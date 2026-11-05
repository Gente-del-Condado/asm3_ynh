"""Optional OIDC relying party. Signed identities never link by email or username."""
import base64
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import ynh_auth as auth

_lock = threading.RLock()
_used_states = {}


def https_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise auth.AccessDenied('Invalid OIDC endpoint')
    url = urlsplit(value)
    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.fragment:
        raise auth.AccessDenied('OIDC requires HTTPS endpoints')
    return value


def config(path=None):
    if path is None:
        from asm3.sitedefs import get_string
        path = get_string('ynh_oidc_config')
    if not path:
        return {'enabled': False}
    try:
        data = json.loads(Path(path).read_text())
        if not isinstance(data, dict) or type(data.get('enabled', False)) is not bool:
            raise ValueError()
        if not data.get('enabled'):
            return {'enabled': False}
        https_url(data['issuer'])
        if urlsplit(data['issuer']).query or len(data['issuer']) > 512:
            raise ValueError()
        if not isinstance(data['client_id'], str) or not data['client_id']:
            raise ValueError()
        method = data.setdefault('token_endpoint_auth_method', 'client_secret_basic')
        if method not in ('client_secret_basic', 'client_secret_post', 'none'):
            raise ValueError()
        if method != 'none' and not isinstance(data.get('client_secret'), str):
            raise ValueError()
        if method != 'none' and not data['client_secret']:
            raise ValueError()
        for key in ('allowed_subjects', 'allowed_groups'):
            data.setdefault(key, [])
            if not isinstance(data[key], list) or not all(isinstance(x, str) and x for x in data[key]):
                raise ValueError()
        links = data.setdefault('ldap_links', {})
        if not isinstance(links, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in links.items()):
            raise ValueError()
        scopes = data.setdefault('scopes', ['openid', 'profile', 'email'])
        if not isinstance(scopes, list) or 'openid' not in scopes or not all(isinstance(s, str) and s and ' ' not in s for s in scopes):
            raise ValueError()
        data.setdefault('groups_claim', 'groups')
        if not isinstance(data['groups_claim'], str):
            raise ValueError()
        age = data.setdefault('session_max_age', 3600)
        if type(age) is not int or not 60 <= age <= 86400:
            raise ValueError()
        if data.get('ca_bundle') and (not isinstance(data['ca_bundle'], str) or not Path(data['ca_bundle']).is_absolute()):
            raise ValueError()
        return data
    except Exception:
        raise auth.AccessDenied('OIDC configuration is invalid') from None


def fingerprint(cfg):
    from asm3.sitedefs import BASE_URL
    return hashlib.sha256((json.dumps(cfg, sort_keys=True) + BASE_URL).encode()).hexdigest()


def request_json(cfg, url, data=None, basic=None):
    import requests
    https_url(url)
    # No environment proxies, redirect following, token logging or unbounded bodies.
    try:
        with requests.Session() as client:
            client.trust_env = False
            with client.request('POST' if data is not None else 'GET', url, data=data,
                                auth=basic, timeout=(3, 8), allow_redirects=False,
                                verify=cfg.get('ca_bundle') or True, stream=True) as response:
                if response.status_code != 200:
                    raise ValueError()
                body = bytearray()
                for chunk in response.iter_content(16384):
                    body.extend(chunk)
                    if len(body) > 1048576:
                        raise ValueError()
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise ValueError()
                return result
    except Exception:
        raise auth.AccessDenied('OIDC provider request failed') from None


def discovery(cfg):
    result = request_json(cfg, cfg['issuer'].rstrip('/') + '/.well-known/openid-configuration')
    if result.get('issuer') != cfg['issuer']:
        raise auth.AccessDenied('OIDC discovery issuer mismatch')
    for key in ('authorization_endpoint', 'token_endpoint', 'jwks_uri'):
        https_url(result.get(key))
    if 'code' not in result.get('response_types_supported', []):
        raise auth.AccessDenied('OIDC provider does not support authorization codes')
    if 'RS256' not in result.get('id_token_signing_alg_values_supported', []):
        raise auth.AccessDenied('OIDC provider must support RS256')
    if 'code_challenge_methods_supported' in result and 'S256' not in result['code_challenge_methods_supported']:
        raise auth.AccessDenied('OIDC provider must support PKCE S256')
    if cfg['token_endpoint_auth_method'] not in result.get('token_endpoint_auth_methods_supported', ['client_secret_basic']):
        raise auth.AccessDenied('OIDC client authentication method is unsupported')
    if result.get('end_session_endpoint'):
        https_url(result['end_session_endpoint'])
    return result


def allowed(cfg, claims):
    groups = claims.get(cfg['groups_claim'], [])
    if not isinstance(groups, list) or not all(isinstance(g, str) for g in groups):
        groups = []
    return claims.get('sub') in cfg['allowed_subjects'] or bool(set(groups) & set(cfg['allowed_groups']))


def verify_token(cfg, metadata, token, nonce):
    import jwt
    try:
        if not isinstance(token, str) or len(token) > 65536:
            raise ValueError()
        header = jwt.get_unverified_header(token)
        if header.get('alg') != 'RS256' or any(k in header for k in ('jku', 'jwk', 'x5u', 'crit')):
            raise ValueError()
        keys = request_json(cfg, metadata['jwks_uri']).get('keys', [])
        keys = [k for k in keys if isinstance(k, dict) and k.get('kty') == 'RSA'
                and k.get('use', 'sig') == 'sig' and k.get('alg', 'RS256') == 'RS256'
                and ('verify' in k.get('key_ops', ['verify']))
                and (not header.get('kid') or k.get('kid') == header['kid'])]
        if len(keys) != 1 or 'd' in keys[0]:
            raise ValueError()
        key = jwt.PyJWK.from_dict(keys[0], algorithm='RS256').key
        if key.key_size < 2048:
            raise ValueError()
        claims = jwt.decode(token, key, algorithms=['RS256'], audience=cfg['client_id'], issuer=cfg['issuer'],
                            options={'require': ['iss', 'sub', 'aud', 'exp', 'iat', 'nonce']}, leeway=15)
        # PyJWT 2.6 (Debian 12) does not validate subject/azp types itself.
        if claims['iss'] != cfg['issuer'] or claims['iat'] > time.time() + 15:
            raise ValueError()
        sub = claims['sub']
        if not isinstance(sub, str) or not 1 <= len(sub) <= 255 or any(ord(c) < 32 or ord(c) > 126 for c in sub):
            raise ValueError()
        if type(claims['exp']) is not int or type(claims['iat']) is not int or claims['exp'] <= time.time():
            raise ValueError()
        aud = claims['aud']
        if aud != cfg['client_id'] and aud != [cfg['client_id']]:
            # Deliberately support one registered audience; no cross-client tokens.
            raise ValueError()
        if 'azp' in claims and claims['azp'] != cfg['client_id']:
            raise ValueError()
        if not isinstance(claims['nonce'], str) or not hmac.compare_digest(claims['nonce'].encode(), nonce.encode()):
            raise ValueError()
        if not allowed(cfg, claims):
            raise auth.AccessDenied('OIDC identity is not authorized')
        return claims
    except auth.AccessDenied:
        raise
    except Exception:
        raise auth.AccessDenied('OIDC ID token validation failed') from None


def identity_key(issuer, subject):
    return hashlib.sha256((issuer + '\0' + subject).encode()).hexdigest()


def setup(dbo):
    dbo.execute('CREATE TABLE IF NOT EXISTS ynh_oidc_identity (IdentityKey CHAR(64) PRIMARY KEY, Issuer VARCHAR(512) NOT NULL, Subject VARCHAR(255) NOT NULL, UserID INTEGER NOT NULL UNIQUE, LDAPSubject VARCHAR(64) NOT NULL)')


def provision(dbo, cfg, claims):
    """Allowlist first. Linking to LDAP is explicit root-controlled configuration."""
    import asm3.users
    if not allowed(cfg, claims):
        raise auth.AccessDenied('OIDC identity is not authorized')
    key = identity_key(cfg['issuer'], claims['sub'])
    with auth._lock:
        rows = dbo.query('SELECT * FROM ynh_oidc_identity WHERE IdentityKey=?', [key])
        link = cfg['ldap_links'].get(claims['sub'])
        person = auth.directory_user(link) if link else None
        if rows:
            row = rows[0]
            if row.ISSUER != cfg['issuer'] or row.SUBJECT != claims['sub']:
                raise auth.AccessDenied('OIDC identity mismatch')
            if (row.LDAPSUBJECT or '') != (person['subject'] if person else ''):
                raise auth.AccessDenied('OIDC account linking requires explicit migration')
            if person:
                user = auth.provision(dbo, person)
                if user.ID != row.USERID:
                    raise auth.AccessDenied('OIDC LDAP profile mismatch')
            user_rows = dbo.query('SELECT * FROM users WHERE ID=?', [row.USERID])
            if not user_rows:
                raise auth.AccessDenied('OIDC profile has been removed')
            user = user_rows[0]
        else:
            if person:
                user = auth.provision(dbo, person)
                userid = user.ID
            else:
                username = 'oidc_' + key
                if dbo.query('SELECT ID FROM users WHERE LOWER(UserName)=LOWER(?)', [username]):
                    raise auth.AccessDenied('Existing local account cannot be claimed by OIDC')
                role = dbo.query_string("SELECT Value FROM ynh_auth_config WHERE Name='default_role'")
                userid = auth.new_user(dbo, username, str(claims.get('name', ''))[:100],
                                       str(claims.get('email', ''))[:100] if claims.get('email_verified') is True else '',
                                       secrets.token_urlsafe(48), roles=role)
            if dbo.query('SELECT UserID FROM ynh_oidc_identity WHERE UserID=?', [userid]):
                raise auth.AccessDenied('Profile is already linked to another OIDC identity')
            dbo.execute('INSERT INTO ynh_oidc_identity (IdentityKey, Issuer, Subject, UserID, LDAPSubject) VALUES (?, ?, ?, ?, ?)',
                        [key, cfg['issuer'], claims['sub'], userid, person['subject'] if person else ''])
            user = dbo.query('SELECT * FROM users WHERE ID=?', [userid])[0]
        if user.DISABLELOGIN:
            raise auth.AccessDenied('ASM3 account is disabled')
        if not person:
            name = str(claims.get('name', ''))[:100]
            email = str(claims.get('email', ''))[:100] if claims.get('email_verified') is True else ''
            dbo.execute('UPDATE users SET RealName=?, EmailAddress=? WHERE ID=?', [name, email, user.ID])
        return user


def checked_identity(session, cfg):
    identity = session.get('oidc_identity')
    if (not cfg.get('enabled') or not identity or identity['fingerprint'] != fingerprint(cfg)
            or identity['deadline'] <= time.time() or not allowed(cfg, identity['claims'])):
        raise auth.AccessDenied('OIDC session expired or policy changed')
    return identity


def start_session(dbo, session, user, identity, path):
    auth.start_session(dbo, session, user, {'subject': identity['key'], 'uid': user.USERNAME}, path)
    session.ynh_source = 'oidc'
    session.oidc_identity = identity


def authenticate_challenge(dbo, session, username, password):
    import web070 as web
    if web.ctx.path not in ('/login', '/mobile_login') or web.ctx.method != 'POST':
        return None
    try:
        identity = checked_identity(session, config())
        if session.get('ynh_challenge_expires', 0) < time.time() or username != session.get('ynh_pending_uid'):
            return None
        if not hmac.compare_digest(str(password).encode(), session.get('ynh_login_token', '').encode()):
            return None
        return provision(dbo, config(), identity['claims'])
    except auth.AccessDenied:
        return None


def mark_login(dbo, session, username):
    identity = checked_identity(session, config())
    user = provision(dbo, config(), identity['claims'])
    if user.USERNAME != username:
        raise auth.AccessDenied('OIDC challenge identity changed')
    try:
        del session.store[session.session_id]
    except KeyError:
        pass
    session.session_id = session._generate_session_id()
    session.ynh_source = 'oidc'
    session.ynh_pending_provider = ''
    session.ynh_login_token = ''
    return True


def begin(session, cfg):
    from asm3.sitedefs import BASE_URL
    metadata = discovery(cfg)
    auth.reset_session(session)
    transaction = {'state': secrets.token_urlsafe(32), 'nonce': secrets.token_urlsafe(32),
                   'verifier': secrets.token_urlsafe(48), 'expires': time.time() + 300,
                   'fingerprint': fingerprint(cfg), 'redirect_uri': BASE_URL + '/oidc/callback'}
    session.oidc_transaction = transaction
    challenge = base64.urlsafe_b64encode(hashlib.sha256(transaction['verifier'].encode()).digest()).rstrip(b'=').decode()
    query = {'client_id': cfg['client_id'], 'response_type': 'code', 'response_mode': 'query',
             'redirect_uri': transaction['redirect_uri'], 'scope': ' '.join(cfg['scopes']),
             'state': transaction['state'], 'nonce': transaction['nonce'],
             'code_challenge': challenge, 'code_challenge_method': 'S256'}
    return metadata['authorization_endpoint'] + ('&' if '?' in metadata['authorization_endpoint'] else '?') + urlencode(query)


def callback(session, cfg, query, dbo, path):
    params = parse_qs(query.lstrip('?'), keep_blank_values=True, max_num_fields=20)
    transaction = session.pop('oidc_transaction', None)
    with _lock:
        now = time.time()
        for key, expires in list(_used_states.items()):
            if expires < now:
                del _used_states[key]
        if (not transaction or transaction['expires'] < now or transaction['fingerprint'] != fingerprint(cfg)
                or len(params.get('state', [])) != 1 or len(params.get('code', [])) != 1
                or 'error' in params or ('iss' in params and params['iss'] != [cfg['issuer']])
                or not hmac.compare_digest(params['state'][0].encode(), transaction['state'].encode())
                or transaction['state'] in _used_states or len(_used_states) >= 10000):
            raise auth.AccessDenied('OIDC state is missing, expired or already used')
        _used_states[transaction['state']] = now + 300
    code = params['code'][0]
    if not code or len(code) > 4096:
        raise auth.AccessDenied('Invalid OIDC authorization code')
    metadata = discovery(cfg)
    body = {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': transaction['redirect_uri'],
            'code_verifier': transaction['verifier']}
    basic = None
    method = cfg['token_endpoint_auth_method']
    if method == 'client_secret_basic':
        # OAuth basic credentials use application/x-www-form-urlencoded encoding.
        from urllib.parse import quote_plus
        basic = (quote_plus(cfg['client_id']), quote_plus(cfg['client_secret']))
    else:
        body['client_id'] = cfg['client_id']
        if method == 'client_secret_post':
            body['client_secret'] = cfg['client_secret']
    tokens = request_json(cfg, metadata['token_endpoint'], data=body, basic=basic)
    claims = verify_token(cfg, metadata, tokens.get('id_token'), transaction['nonce'])
    # Store only verified identity attributes; never store access/refresh/ID tokens.
    keep = {k: claims[k] for k in ('iss', 'sub', 'iat', 'exp', 'name', 'email', 'email_verified', cfg['groups_claim']) if k in claims}
    identity = {'claims': keep, 'fingerprint': fingerprint(cfg), 'key': identity_key(cfg['issuer'], claims['sub']),
                'deadline': min(claims['exp'], time.time() + cfg['session_max_age'])}
    user = provision(dbo, cfg, claims)
    import asm3.users
    import web070 as web
    if not asm3.users.authenticate_ip(user, web.ctx.ip):
        raise auth.AccessDenied('ASM3 IP restriction denied access')
    if user.get('ENABLETOTP', 0):
        auth.reset_session(session)
        session.oidc_identity = identity
        session.ynh_pending_provider = 'oidc'
        session.ynh_pending_uid = user.USERNAME
        session.ynh_login_token = secrets.token_urlsafe(32)
        session.ynh_challenge_expires = min(time.time() + 300, identity['deadline'])
        return '/login'
    start_session(dbo, session, user, identity, path)
    return '/main'


def dispatch(session, path):
    """True means a validated OIDC session may enter the native ASM3 handler."""
    import web070 as web
    import asm3.db
    import asm3.users
    from asm3.sitedefs import BASE_URL
    route = web.ctx.path
    if route == '/ynh_sso':
        if session.get('ynh_source') == 'oidc' or session.get('ynh_pending_provider') == 'oidc':
            auth.reset_session(session)
        return False
    active = session.get('ynh_source') == 'oidc' or session.get('ynh_pending_provider') == 'oidc'
    if not route.startswith('/oidc/') and not active:
        return False
    redirect = None
    try:
        cfg = config()
        if not cfg.get('enabled'):
            raise auth.AccessDenied('OpenID Connect is disabled')
        if web.ctx.method != 'GET' and route.startswith('/oidc/'):
            raise auth.AccessDenied('OIDC endpoints require GET')
        if route == '/oidc/login':
            redirect = begin(session, cfg)
        elif route == '/oidc/callback':
            if len(web.ctx.query) > 8192:
                raise auth.AccessDenied('Invalid OIDC response')
            dbo = asm3.db.get_database()
            dbo.installpath = path
            redirect = BASE_URL + callback(session, cfg, web.ctx.query, dbo, path)
        elif route == '/oidc/logout':
            if session.get('user'):
                asm3.users.logout(session, web.ctx.ip, web.ctx.env.get('HTTP_USER_AGENT', ''))
            auth.reset_session(session)
            session.ynh_logged_out = True
            redirect = BASE_URL + '/login?loggedout=1'
            try:
                endpoint = discovery(cfg).get('end_session_endpoint')
                if endpoint:
                    session.oidc_logout_state = secrets.token_urlsafe(32)
                    redirect = endpoint + ('&' if '?' in endpoint else '?') + urlencode({
                        'client_id': cfg['client_id'], 'post_logout_redirect_uri': BASE_URL + '/oidc/logged_out',
                        'state': session.oidc_logout_state})
            except auth.AccessDenied:
                pass  # Local logout remains effective during provider outages.
        elif route == '/oidc/logged_out':
            state = web.input().get('state', '')
            expected = session.pop('oidc_logout_state', '')
            if not expected or not hmac.compare_digest(state.encode(), expected.encode()):
                raise auth.AccessDenied('Invalid OIDC logout state')
            redirect = BASE_URL + '/login?loggedout=1'
        elif route.startswith('/oidc/'):
            raise auth.AccessDenied('Unknown OIDC endpoint')
        else:
            identity = checked_identity(session, cfg)
            dbo = asm3.db.get_database()
            dbo.installpath = path
            user = provision(dbo, cfg, identity['claims'])
            if not asm3.users.authenticate_ip(user, web.ctx.ip):
                raise auth.AccessDenied('ASM3 IP restriction denied access')
            if session.get('ynh_pending_provider') == 'oidc':
                if session.get('ynh_challenge_expires', 0) < time.time():
                    raise auth.AccessDenied('OIDC second factor challenge expired')
                if route not in ('/login', '/mobile_login', '/config.js'):
                    redirect = BASE_URL + '/login'
            else:
                asm3.users.update_session(dbo, session, user.USERNAME)
                if route in ('/login', '/mobile_login'):
                    redirect = BASE_URL + '/main'
    except (auth.AccessDenied, ValueError, KeyError, TypeError):
        auth.reset_session(session)
        raise web.forbidden('OpenID Connect authentication failed') from None
    if redirect:
        raise web.seeother(redirect)
    return True
