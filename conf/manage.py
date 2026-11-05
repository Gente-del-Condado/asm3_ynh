"""Offline schema setup and upgrade, using ASM3 APIs. Password arrives on stdin."""
import secrets
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "upstream/src"
sys.path.insert(0, str(SRC))


def import_forms(dbo):
    import asm3.onlineform
    for path in sorted((SRC / "media/onlineform").glob("*.json")):
        data = json.loads(path.read_text())
        # 51-1 contains a duplicate 'reaction' field in an RSPCA form.
        # Keep every field, assigning a unique name to repeated occurrences.
        used = set()
        for field in data["fields"]:
            base = field["name"]
            name = base
            suffix = 2
            while name.upper() in used:
                name = f"{base}{suffix}"
                suffix += 1
            field["name"] = name
            used.add(name.upper())
        form_id = asm3.onlineform.import_onlineform_json(dbo, json.dumps(data))
        actual = dbo.query_int("SELECT COUNT(*) FROM onlineformfield WHERE OnlineFormID=?", [form_id])
        if actual != len(data["fields"]):
            raise RuntimeError(f"Incomplete online form: {path.name}")


def manage(mode, admin=None, locale=None):
    import asm3.db
    import asm3.dbupdate as updates
    import asm3.users as users
    import asm3.configuration as configuration
    import asm3.reports as reports
    from asm3.sitedefs import LOCALE

    dbo = asm3.db.get_database()
    dbo.installpath = str(SRC) + "/"
    if mode == "install":
        if dbo.query_int("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()"):
            raise RuntimeError("Refusing to initialize an existing database")
        password = sys.stdin.read()
        if not password or not admin:
            raise ValueError("Administrator and password are required")
        dbo.locale = locale
        # Initialize even when sheltermanager.com's online catalogue is unavailable.
        # Runtime keeps the default online catalogue for future report updates.
        reports.URL_REPORTS = (SRC.parent / "reports/reports.txt").as_uri()
        # Same phases as dbupdate.install(), with explicit error checks and
        # fixes for bundled forms on MariaDB's default strict SQL mode.
        updates.install_db_structure(dbo)
        dbo.execute("ALTER TABLE onlineformfield MODIFY Label TEXT NOT NULL")
        if updates.install_db_views(dbo):
            raise RuntimeError("Could not initialize database views")
        updates.install_default_data(dbo)
        # configuration.get_map merges upstream defaults, including Locale=en;
        # setting only asm3.conf or dbo.locale does not persist the UI language.
        configuration.cset(dbo, "Locale", locale)
        if updates.install_db_sequences(dbo):
            raise RuntimeError("Could not initialize database sequences")
        updates.install_db_stored_procedures(dbo)
        updates.install_default_templates(dbo)
        import_forms(dbo)
        updates.install_default_reports(dbo)
        # Disable both upstream default accounts before the listener is started.
        dbo.execute("UPDATE users SET DisableLogin = 1, Password = ?", [users.hash_password(secrets.token_urlsafe(48))])
        dbo.execute(
            "UPDATE users SET UserName = ?, RealName = ?, Password = ?, DisableLogin = 0 WHERE ID = 1",
            [admin, admin, users.hash_password(password)],
        )
        import ynh_auth
        if not ynh_auth.enabled() and not users.authenticate(dbo, admin, password):
            raise RuntimeError("Administrator verification failed")
    elif mode == "upgrade":
        _, errors = updates.perform_updates(dbo)
        if errors:
            raise RuntimeError(f"ASM3 database migration failed ({errors} errors)")
        if updates.install_db_views(dbo):
            raise RuntimeError("ASM3 database view update failed")
        if updates.install_db_sequences(dbo):
            raise RuntimeError("ASM3 database sequence update failed")
        if not dbo.query_int("SELECT COUNT(*) FROM configuration WHERE ItemName='Locale'"):
            configuration.cset(dbo, "Locale", LOCALE)
    else:
        raise ValueError("Expected install or upgrade")
    import ynh_auth
    if ynh_auth.enabled():
        rescue_password = password if mode == "install" else sys.stdin.read()
        if not rescue_password or not admin:
            raise ValueError("Recovery secret and selected administrator are required")
        ynh_auth.setup(dbo, admin, rescue_password)
    # Verify every expected table, including the 51 -> 51-1 salesreceipt fix.
    for table in updates.TABLES:
        dbo.query(f"SELECT * FROM {table} WHERE 1 = 0")
    print(f"ASM3 {mode}: schema {configuration.dbv(dbo)} verified")


if __name__ == "__main__":
    manage(*sys.argv[1:])
