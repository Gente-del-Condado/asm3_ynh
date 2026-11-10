# Desarrollo y mantenimiento del paquete

El proyecto empaqueta Animal Shelter Manager como aplicación nativa de YunoHost.
El núcleo de ASM3 se mantiene en el repositorio de Shelter Manager. Aquí se
mantienen el instalador, las adaptaciones de identidad, la automatización y
las guías.

## Mapa del código

| Ruta | Responsabilidad |
| --- | --- |
| `manifest.toml`, `upstream.lock.json` | Versión, requisitos, permisos, recursos y origen fijado por commit y SHA-256 |
| `scripts/`, `hooks/` | Ciclo de vida de la app y sincronización con Dex |
| `conf/asm3.conf`, `nginx.conf`, `systemd.service`, `cron` dentro de `conf/` | Plantillas de configuración del servidor |
| `conf/build.py`, `manage.py`, `server.py` dentro de `conf/` | Generación de recursos, inicialización/migraciones y servidor WSGI |
| `conf/ynh_auth.py`, `ynh_oidc.py`, `ynh_mfa.py` dentro de `conf/` | SSO LDAP, identidad OIDC y segundo factor |
| `config_panel.toml`, `conf/manage_identity.py`, `conf/manage_oidc.py` | Configuración de identidad, restauración y reversión |
| `patches/main/` | Adaptaciones mínimas al código descargado de ASM3 |
| `tests/`, `tests.toml`, `tools/` | Pruebas, comprobaciones, actualización y empaquetado |
| `doc/`, `docs/` | Documentación de YunoHost y sitio estático respectivamente |
| `.github/workflows/`, `.forgejo/workflows/` | Validación, actualización upstream y matriz de laboratorio |

## Flujo de ejecución

1. YunoHost aprovisiona la cuenta de servicio, MariaDB y los directorios.
   `scripts/_common.sh` aplica plantillas, copia adaptadores y prepara el código.
2. Nginx pasa las peticiones al proceso local de `conf/server.py`. La cabecera
   de identidad solo se acepta detrás del proxy autorizado.
3. Los adaptadores autentican y vinculan la identidad con un perfil local.
   MFA completa la sesión antes de exponer datos privados.
4. Los trabajos programados, las copias y las migraciones comparten el bloqueo
   de mantenimiento de cada instancia. Los documentos persistentes viven en MariaDB.

## Ejecutar comprobaciones

Usa Python 3.11 o superior, ShellCheck y un entorno virtual. En Debian también
puedes instalar las dependencias Python equivalentes con APT.

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install jsonschema PyJWT cryptography PyYAML
python tools/check_package.py
python -m unittest discover -s tests -v
python -m http.server 8000 --bind 127.0.0.1 --directory docs
```

Prueba el manual en `http://127.0.0.1:8000/` y verifica navegación, ejemplos e
imágenes en escritorio y móvil. Consulta [pruebas](doc/TESTING.md) para
MariaDB, autenticación y `package_check`. Los logs completos se quedan en el
laboratorio salvo que hayan sido revisados. Los informes publicables se
guardan en [doc/validation](doc/validation/README.md) junto con la revisión probada.

## Actualizar el origen y publicar

Ejecuta `python tools/update_upstream.py` para buscar la versión estable y
revisar la propuesta. Inspecciona el cambio, aplica los parches a la nueva
versión, revisa los cambios de esquema y prueba instalación y actualización.
Deja las dependencias y permisos declarados en el manifest. Comprueba las
instrucciones de [publicación](doc/PUBLISHING.md) para GitHub Pages y Forgejo.

`bash tools/build_release.sh` genera el tar y el bundle en `dist/`. El bundle
generado es una instantánea instalable. Para conservar todo el historial al
publicar, parte del repositorio Git y empuja su rama.
