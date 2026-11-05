"""Directory-backed YunoHost identity bridge. No YunoHost password enters ASM3."""
import copy
import hmac
import secrets
import threading
import time

_lock = threading.RLock()
PUBLIC_PATHS = frozenset(("/service", "/custom_logo", "/custom_splash", "/favicon.ico",
                          "/pp_cardcom", "/pp_paypal", "/pp_stripe", "/pp_square"))


class AccessDenied(Exception):
    pass


def enabled():
    from asm3.sitedefs import get_boolean
    return get_boolean("ynh_sso", False)


def directory_user(uid, require_permission=True):
    """Anonymous read of local LDAP; referrals disabled; no cached grants."""
    import re
    from ldap3 import Connection, Server, NONE, SUBTREE
    from ldap3.utils.conv import escape_filter_chars
    from asm3.sitedefs import get_string
    if not re.fullmatch(r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,99}", uid or ""):
        raise AccessDenied("Invalid YunoHost identity")
    app = get_string("ynh_instance")
    search = f"(&(objectClass=posixAccount)(uid={escape_filter_chars(uid)}))"
    if require_permission:
        search = f"(&{search}(permission=cn={escape_filter_chars(app)}.staff,ou=permission,dc=yunohost,dc=org))"
    try:
        with Connection(Server("127.0.0.1", port=389, get_info=NONE, connect_timeout=3),
                        auto_bind=True, receive_timeout=3, auto_referrals=False,
                        read_only=True, raise_exceptions=True) as conn:
            conn.search("ou=users,dc=yunohost,dc=org", search, search_scope=SUBTREE,
                        attributes=["uid", "entryUUID", "displayName", "mail"], size_limit=2, time_limit=3)
            rows = [r for r in conn.response if r.get("type") == "searchResEntry"]
            if len(rows) != 1:
                raise AccessDenied("YunoHost account missing or not authorized for ASM3 staff")
            attrs = {k.lower(): v for k, v in rows[0]["attributes"].items()}
            def first(key):
                value = attrs.get(key, [])
                return str(value[0] if isinstance(value, list) and value else value or "")
            result = {"uid": first("uid"), "subject": first("entryuuid"),
                      "name": first("displayname"), "email": first("mail")}
            if not result["subject"] or result["uid"].lower() != uid.lower():
                raise AccessDenied("Directory identity has no stable identifier")
            return result
    except AccessDenied:
        raise
    except Exception:
        # Deliberately do not include library exceptions, LDAP values or secrets.
        raise AccessDenied("YunoHost directory is unavailable") from None


def identity_row(dbo, subject):
    return dbo.query("SELECT UserID FROM ynh_auth_identity WHERE Subject=?", [subject])


def is_managed(dbo, username):
    return bool(dbo.query("SELECT i.UserID FROM ynh_auth_identity i INNER JOIN users u ON u.ID=i.UserID WHERE LOWER(u.UserName)=LOWER(?)", [username]))


def new_user(dbo, username, name, email, password, superuser=False, roles=""):
    import asm3.users
    from asm3.utils import PostedData
    return asm3.users.insert_user_from_form(dbo, "ynh-provision", PostedData({
        "username": username, "realname": name, "email": email, "password": password,
        "superuser": "1" if superuser else "0", "disablelogin": "0", "roles": roles,
    }, dbo.locale))


def setup(dbo, admin, rescue_password):
    """Run only during install/upgrade, with the service stopped."""
    from asm3.sitedefs import get_string
    import asm3.users
    dbo.execute("CREATE TABLE IF NOT EXISTS ynh_auth_identity (Subject VARCHAR(64) PRIMARY KEY, UserID INTEGER NOT NULL UNIQUE)")
    dbo.execute("CREATE TABLE IF NOT EXISTS ynh_auth_config (Name VARCHAR(64) PRIMARY KEY, Value VARCHAR(255) NOT NULL)")
    if not dbo.query("SELECT Value FROM ynh_auth_config WHERE Name='default_role'"):
        role = dbo.insert("role", {"RoleName": "YunoHost (read only)", "SecurityMap": "va *"}, setCreated=False)
        dbo.execute("INSERT INTO ynh_auth_config (Name, Value) VALUES ('default_role', ?)", [str(role)])
    rescue = "ynh_rescue_" + get_string("ynh_instance")
    if not dbo.query("SELECT ID FROM users WHERE UserName=?", [rescue]):
        new_user(dbo, rescue, "Local recovery administrator", "", rescue_password, superuser=True)
    # Only the administrator explicitly selected in the installer is linked to an
    # existing account. Other collisions are denied instead of silently claimed.
    if not dbo.query("SELECT UserID FROM ynh_auth_identity WHERE UserID=1"):
        existing = dbo.query("SELECT UserName FROM users WHERE ID=1")
        if not existing or existing[0].USERNAME.lower() != admin.lower():
            raise AccessDenied("Initial administrator was renamed; explicit account migration required")
        person = directory_user(admin, require_permission=False)
        dbo.execute("INSERT INTO ynh_auth_identity (Subject, UserID) VALUES (?, 1)", [person["subject"]])
        dbo.execute("UPDATE users SET Password=? WHERE ID=1", [asm3.users.hash_password(secrets.token_urlsafe(48))])


def provision(dbo, person):
    """Map by LDAP entryUUID. Never overwrite local collisions or assigned roles."""
    with _lock:
        mapped = identity_row(dbo, person["subject"])
        if mapped:
            userid = mapped[0].USERID
        else:
            if dbo.query("SELECT ID FROM users WHERE LOWER(UserName)=LOWER(?)", [person["uid"]]):
                raise AccessDenied("Existing local account requires explicit linking")
            role = dbo.query_string("SELECT Value FROM ynh_auth_config WHERE Name='default_role'")
            userid = new_user(dbo, person["uid"], person["name"], person["email"], secrets.token_urlsafe(48), roles=role)
            dbo.execute("INSERT INTO ynh_auth_identity (Subject, UserID) VALUES (?, ?)", [person["subject"], userid])
        user = dbo.query("SELECT * FROM users WHERE ID=?", [userid])[0]
        if user.DISABLELOGIN:
            raise AccessDenied("ASM3 account is disabled")
        if user.REALNAME != person["name"] or user.EMAILADDRESS != person["email"]:
            dbo.execute("UPDATE users SET RealName=?, EmailAddress=? WHERE ID=?", [person["name"], person["email"], userid])
        return user


def reset_session(session):
    """Invalidate the old identifier and all identity/role data, including TOTP."""
    try:
        del session.store[session.session_id]
    except KeyError:
        pass
    ip = session.get("ip", "127.0.0.1")
    session._data.clear()
    session.update(copy.deepcopy(session._initializer))
    session.session_id = session._generate_session_id()
    session.ip = ip
    session.send_cookie = True
    session._killed = False


def start_session(dbo, session, user, person, path):
    import asm3.users
    import asm3.configuration
    import asm3.audit
    import web070 as web
    reset_session(session)
    dbo.installpath = path
    dbo.locked = asm3.configuration.smdb_locked(dbo)
    dbo.timezone = asm3.configuration.timezone(dbo)
    dbo.timezone_dst = asm3.configuration.timezone_dst(dbo)
    dbo.locale = asm3.configuration.locale(dbo)
    session.nologconnection = False
    session.force2fa = asm3.configuration.force_2fa(dbo) and not user.get("ENABLETOTP", 0)
    asm3.users.update_session(dbo, session, user.USERNAME)
    session.ynh_subject = person["subject"]
    session.ynh_uid = person["uid"]
    session.ynh_source = "sso"
    asm3.audit.login(dbo, user.USERNAME, web.ctx.ip, web.ctx.env.get("HTTP_USER_AGENT", ""))
    asm3.users.update_user_activity(dbo, user.USERNAME)


def authenticate_challenge(dbo, username, password):
    """Let ASM3's existing login flow check TOTP using a session-bound nonce."""
    import asm3.utils
    import web070 as web
    session = asm3.utils.websession
    if web.ctx.path not in ("/login", "/mobile_login") or web.ctx.method != "POST":
        return None
    if not session or not session.get("ynh_login_token") or session.get("ynh_challenge_expires", 0) < time.time():
        return None
    uid = web.ctx.env.get("asm3.ynh_user", "")
    if not uid or uid.lower() != username.lower() or not hmac.compare_digest(str(password), session.ynh_login_token):
        return None
    try:
        person = directory_user(uid)
        if person["subject"] != session.get("ynh_pending_subject"):
            return None
        return provision(dbo, person)
    except AccessDenied:
        return None


def mark_login(dbo, session, username):
    """Called by web_login only after all native password/TOTP/IP checks pass."""
    if is_managed(dbo, username):
        import web070 as web
        person = directory_user(web.ctx.env.get("asm3.ynh_user", ""))
        if person["subject"] != session.get("ynh_pending_subject"):
            raise AccessDenied("SSO challenge identity changed")
        # Rotate the identifier without discarding the session assembled by ASM3.
        try:
            del session.store[session.session_id]
        except KeyError:
            pass
        session.session_id = session._generate_session_id()
        session.ynh_source = "sso"
        session.ynh_subject = person["subject"]
        session.ynh_uid = person["uid"]
        session.ynh_login_token = ""
        return True
    session.ynh_source = "local"
    session.ynh_subject = ""
    session.ynh_login_token = ""
    session.ynh_local_mode = True
    return False


def login_hint(session):
    if session.get("ynh_login_token"):
        return {"husername": session.get("ynh_pending_uid"), "hpassword": session.ynh_login_token}
    return {}


def processor(session, installpath):
    """Installed after web.py's session processor, never around shared globals."""
    import web070 as web
    import asm3.db
    import asm3.users
    from asm3.sitedefs import BASE_URL

    def run(handler):
        path = web.ctx.path
        if path.startswith("/static/") or path in PUBLIC_PATHS:
            return handler()
        uid = web.ctx.env.get("asm3.ynh_user", "")
        params = web.input()
        if path in ("/logout", "/mobile_logout") and session.get("user"):
            asm3.users.logout(session, web.ctx.ip, web.ctx.env.get("HTTP_USER_AGENT", ""))
            reset_session(session)
            session.ynh_logged_out = True
            raise web.seeother(BASE_URL + "/login?loggedout=1")
        # Local recovery is intentional and separate from externally managed users.
        if path in ("/login", "/mobile_login") and params.get("local") == "1":
            if session.get("ynh_source") == "sso":
                reset_session(session)
            session.ynh_local_mode = True
            return handler()
        if path in ("/login", "/mobile_login") and web.ctx.method == "POST":
            return handler()
        if session.get("ynh_logged_out"):
            if path in ("/", "/ynh_sso"):
                session.ynh_logged_out = False
            else:
                return handler()
        if session.get("ynh_local_mode"):
            if path == "/ynh_sso":
                reset_session(session)
            else:
                return handler()
        if not uid:
            if session.get("ynh_source") == "sso":
                reset_session(session)
            if path == "/ynh_sso":
                raise web.forbidden("A YunoHost portal session is required")
            if path in ("/login", "/mobile_login") and web.ctx.method == "GET":
                raise web.seeother(BASE_URL + "/ynh_sso")
            return handler()
        # A deliberately authenticated local recovery account keeps its own session.
        if session.get("user") and session.get("ynh_source") != "sso" and path != "/ynh_sso":
            return handler()
        try:
            person = directory_user(uid)
            dbo = asm3.db.get_database()
            dbo.installpath = installpath
            user = provision(dbo, person)
            if not asm3.users.authenticate_ip(user, web.ctx.ip):
                raise AccessDenied("ASM3 IP restriction denied access")
            same = session.get("ynh_subject") == person["subject"] and session.get("ynh_source") == "sso"
            if not same:
                if (user.get("ENABLETOTP", 0) and session.get("ynh_pending_subject") == person["subject"]
                        and session.get("ynh_challenge_expires", 0) >= time.time()):
                    if path in ("/login", "/mobile_login", "/config.js"):
                        return handler()
                    raise web.seeother(BASE_URL + "/login")
                reset_session(session)
                if user.get("ENABLETOTP", 0):
                    session.ynh_pending_subject = person["subject"]
                    session.ynh_pending_uid = person["uid"]
                    session.ynh_login_token = secrets.token_urlsafe(32)
                    session.ynh_challenge_expires = time.time() + 300
                    if path not in ("/login", "/mobile_login"):
                        raise web.seeother(BASE_URL + "/login")
                    return handler()
                start_session(dbo, session, user, person, installpath)
            else:
                # Fresh DB state on every private request: role changes and local
                # DisableLogin take effect without waiting for ASM3's username cache.
                asm3.users.update_session(dbo, session, user.USERNAME)
            if path in ("/ynh_sso", "/login", "/mobile_login"):
                raise web.seeother(BASE_URL + ("/mobile" if path == "/mobile_login" else "/main"))
            return handler()
        except AccessDenied as error:
            reset_session(session)
            raise web.forbidden(str(error))
    return run
