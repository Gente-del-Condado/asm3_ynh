"""Instala y actualiza el esquema con las API de ASM3. Recibe la contraseña por stdin."""
import secrets
import os
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "upstream/src"
sys.path.insert(0, str(SRC))


def import_forms(dbo):
    import asm3.onlineform
    for path in sorted((SRC / "media/onlineform").glob("*.json")):
        data = json.loads(path.read_text())
        # Un formulario RSPCA de 51-1 repite el campo reaction.
        # Conserva todos los campos asignando nombres únicos a los repetidos.
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
            raise RuntimeError(f"No se importaron todos los campos del formulario {path.name}")


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
        operation = "Instalación"
        if dbo.query_int("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE()"):
            raise RuntimeError("Se ha detenido la instalación porque la base de datos ya contiene tablas")
        password = sys.stdin.read()
        if not password or not admin:
            raise ValueError("Se requiere el administrador y su contraseña de recuperación")
        print("Preparando la base MariaDB de esta instancia de ASM3…", flush=True)
        dbo.locale = locale
        # Permite inicializar la base sin acceso al catálogo en línea.
        # ASM3 conserva el catálogo en línea para actualizar informes después.
        reports.URL_REPORTS = (SRC.parent / "reports/reports.txt").as_uri()
        # Reproduce las fases de dbupdate.install() con comprobación de errores
        # y adapta los formularios al modo estricto predeterminado de MariaDB.
        updates.install_db_structure(dbo)
        dbo.execute("ALTER TABLE onlineformfield MODIFY Label TEXT NOT NULL")
        if updates.install_db_views(dbo):
            raise RuntimeError("No se pudieron crear las vistas de la base de datos")
        updates.install_default_data(dbo)
        # configuration.get_map incorpora Locale=en de la configuración original.
        # Persiste el idioma en la base para que se conserve en la interfaz.
        configuration.cset(dbo, "Locale", locale)
        if updates.install_db_sequences(dbo):
            raise RuntimeError("No se pudieron inicializar las secuencias de la base de datos")
        updates.install_db_stored_procedures(dbo)
        updates.install_default_templates(dbo)
        print("Cargando los formularios incluidos en ASM3…", flush=True)
        import_forms(dbo)
        updates.install_default_reports(dbo)
        # Deshabilita las cuentas predeterminadas antes de arrancar el servicio.
        dbo.execute("UPDATE users SET DisableLogin = 1, Password = ?", [users.hash_password(secrets.token_urlsafe(48))])
        dbo.execute(
            "UPDATE users SET UserName = ?, RealName = ?, Password = ?, DisableLogin = 0 WHERE ID = 1",
            [admin, admin, users.hash_password(password)],
        )
        import ynh_auth
        if not ynh_auth.enabled() and not users.authenticate(dbo, admin, password):
            raise RuntimeError("Falló la comprobación de la cuenta de administrador")
    elif mode == "upgrade":
        operation = "Actualización"
        print("Comprobando las migraciones de la base MariaDB de ASM3…", flush=True)
        _, errors = updates.perform_updates(dbo)
        if errors:
            raise RuntimeError(f"Falló la migración de la base de datos de ASM3 ({errors} errores)")
        if updates.install_db_views(dbo):
            raise RuntimeError("Falló la actualización de las vistas de la base de datos de ASM3")
        if updates.install_db_sequences(dbo):
            raise RuntimeError("Falló la actualización de las secuencias de la base de datos de ASM3")
        if not dbo.query_int("SELECT COUNT(*) FROM configuration WHERE ItemName='Locale'"):
            configuration.cset(dbo, "Locale", LOCALE)
    else:
        raise ValueError("La operación debe ser install o upgrade")
    import ynh_auth
    if ynh_auth.enabled():
        rescue_password = password if mode == "install" else sys.stdin.read()
        if not rescue_password or not admin:
            raise ValueError("Se requiere la contraseña de recuperación y el administrador seleccionado")
        ynh_auth.setup(dbo, admin, rescue_password)
    # Verifica todas las tablas, incluida salesreceipt tras la migración de 51 a 51-1.
    for table in updates.TABLES:
        dbo.query(f"SELECT * FROM {table} WHERE 1 = 0")
    print(f"{operation} de ASM3 verificada. Versión del esquema: {configuration.dbv(dbo)}.", flush=True)


if __name__ == "__main__":
    os.environ["ASM3_YNH_MAINTENANCE_LOG"] = "1"
    manage(*sys.argv[1:])
