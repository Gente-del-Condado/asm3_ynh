# Validación

Este documento distingue las pruebas locales de la validación integral de YunoHost.

## Comprobaciones rápidas

Requieren Bash, ShellCheck, Python ≥ 3.11, `jsonschema`, PyJWT y `cryptography`:

```bash
python3 tools/check_package.py
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
```

Se verifican los esquemas JSON oficiales de manifest/tests, la coherencia del
commit/versión/SHA-256, los permisos ejecutables, la sintaxis Bash/Python y los
problemas ShellCheck. Los esquemas están copiados en `tests/schemas` desde
[YunoHost/apps](https://github.com/YunoHost/apps/tree/main/schemas) para que las
comprobaciones funcionen sin red. No son el runtime del gestor de paquetes.

Las pruebas unitarias cubren validación criptográfica OIDC, configuración, expiry/state,
proxy y cookies por instancia, rechazo de cabeceras
falsificadas, permisos LDAP, UUID obligatorio, fallos de directorio, aislamiento
de endpoints con datos privados y el actualizador de versiones/API Forgejo.

## Prueba funcional con MariaDB real

En una máquina de desarrollo Debian/Ubuntu con las dependencias del manifest:

```bash
python3 tools/smoke_test.py
# Se puede reutilizar un archivo de upstream ya descargado:
python3 tools/smoke_test.py --archive /ruta/al/archivo-upstream.tar.gz
```

El script valida SHA-256, crea una MariaDB temporal con puerto y socket propios,
instala ASM3 y después elimina los procesos y archivos temporales. No usa ni
modifica la base de datos del servidor. Ejecutarlo como usuario normal con permiso
para abrir puertos locales. Comprueba:

1. Generación de versión, catálogo local y esquema JavaScript.
2. Creación completa de tablas, plantillas, informes y formularios.
3. Administrador activo y cuentas predeterminadas deshabilitadas.
4. Arranque del servicio real, redirecciones HTTPS en raíz/subruta, login HTTP,
   sesión autenticada, cookies por instancia y recurso estático generado.
   Comprueba también que login/API/base64 no escriban contraseñas en logs.
5. Actualización idempotente; aplicación de una migración temporal y rechazo de una
   migración fallida, sin aceptar un éxito falso.
6. Copia SQL, eliminación y recreación de la base, restauración y conservación de
   credenciales y contenido de documentos.

El workflow `ci.yml` hace estas pruebas con `python3-mysqldb` del sistema en Ubuntu.
La ejecución local se realiza en un entorno temporal; las versiones exactas y los
resultados de la entrega se registran más abajo.

## Matriz completa YunoHost

Requiere una máquina preparada con Incus/LXD y los requisitos de
[package_check](https://github.com/YunoHost/package_check). Una vez preparado:

```bash
git clone https://github.com/YunoHost/package_check.git
cd package_check
./package_check.sh /ruta/absoluta/asm3_ynh
```

`tests.toml` activa la matriz predeterminada: instalación en raíz/subruta, varias
instancias, actualización, copia/restauración y cambio de URL. También hay un
workflow manual `package-check.yml` para un runner dedicado con las etiquetas
`self-hosted`, `linux`, `yunohost-package-check`. No se ejecuta automáticamente sobre
PRs en una máquina con privilegios.

Esta prueba valida aspectos que el smoke test no cubre: aprovisionamiento real de
recursos y SSOwat, helper runtime, Nginx, aislamiento de systemd, integración SMTP,
desinstalación y rollback del gestor. No sustituirla por los tests unitarios.

## SSO con YunoHost real

Solo dentro de una instalación **desechable** de laboratorio, como root:

```bash
python3 tools/test_yunohost_sso.py --disposable-lab asm3 --lifecycle
```

El script modifica usuarios y permisos, cambia la contraseña del administrador
ficticio del laboratorio y, con `--lifecycle`, elimina y restaura la aplicación.
No ejecutarlo en producción. Usa LDAP, SSOwat, portal HTTPS, Nginx y ASM3 reales.
Comprueba creación de perfiles y roles, sincronización de nombre/correo, revocación,
bloqueo, cambio de identidad, logout, TOTP, recuperación, colisiones de UUID,
contraseñas ausentes en journal/logs de operaciones y conservación tras restaurar.
El informe se escribe en `/root/asm3-sso-results.json`.

## OpenID Connect con HTTPS real

Dentro del mismo YunoHost desechable, con las dependencias del manifest:

```bash
python3 tools/test_yunohost_oidc.py --disposable-lab asm3 --algorithm RS256 --lifecycle
python3 tools/test_yunohost_oidc.py --disposable-lab asm3 --algorithm RS512 --lifecycle
```

Arranca un proveedor efímero HTTPS con RSA 2048, discovery, JWKS, authorization,
token endpoint y logout. El proveedor exige el verificador PKCE y la misma URI.
Se prueban callbacks reales contra el servicio instalado, tokens inválidos,
state/cookie/replay, política, roles, TOTP, elección entre OIDC y portal, vínculo
LDAP y revocación, recuperación, logs sin tokens y copia/eliminación/restauración.
El informe queda en `/root/asm3-oidc-results.json`. No usar en producción: cambia
usuarios, permisos, configuración y, con `--lifecycle`, elimina la aplicación.
Las claves y secretos del proveedor se generan durante la prueba, no van en Git.

## Dex real y MFA obligatorio (solo laboratorio desechable)

Instala primero el Dex oficial en el mismo servidor y ejecuta como root:

```bash
python3 tools/test_yunohost_dex.py --disposable-lab asm3 --lifecycle
```

Modifica credenciales de laboratorio, fuerza alta de factores, configura los tres
conectores con fixtures, cambia permisos y URL, retira y restaura ASM3. No debe
usarse en producción. Prueba Dex/LDAP completo, alta QR/TOTP, códigos reutilizados,
CSRF, bloqueo persistente, restablecimiento root y revocación de sesiones/pending.
Comprueba las URLs OAuth generadas por los tres conectores, sus callbacks y
`User.Read` en Microsoft sin seguir los logins cloud.
Verifica credenciales especiales en el proceso Dex sin mostrarlas, el getter,
registros, permisos de archivos y coexistencia con un cliente de otra app.
No inicia sesiones contra las cuentas cloud reales.

Las suites SSO/OIDC usan `mfa_lab.py` para completar el factor tras el primer
login. Solo el harness root desechable reinicia el contador TOTP entre logins para
no esperar 30 segundos por cada caso; el código de producción nunca lo reinicia
al autenticar. Los casos específicos Dex prueban replay y bloqueo sin ese ajuste.

## Estado de esta entrega

Validación del **5 de noviembre de 2026**, revisión **51.1~ynh6**.
Las suites incluyen ahora la puerta MFA obligatoria y el Dex real; los recuentos
actuales y sus límites se detallan en la evidencia.
La evidencia definitiva está en [validation/README.md](validation/README.md).
El laboratorio y las imágenes exactas se describen en [LAB.md](LAB.md).

La matriz se ejecuta en Debian 12 / YunoHost 12.1.41.2 / amd64 dentro de Incus
en una VM. El smoke test adicional usa Python 3.14, MariaDB 11.8.8 y mysqlclient
2.3.0. No se ha ejecutado la matriz sobre ARM.

La nota oficial depende también del catálogo comunitario. El wrapper devuelve
error de calidad si es 0, aunque los escenarios funcionales pasen; conserva el
JSON original. No simula pertenencia al catálogo ni altera las pruebas oficiales.
La instalación personalizada desde un repositorio no requiere su alta editorial.

Los hashes de [runtime.sha256](validation/runtime.sha256) permiten comprobar
que el código funcional coincide con el probado, aunque se añadan después los
informes o documentación:

```bash
sha256sum -c doc/validation/runtime.sha256
```

Los workflows se verifican en sintaxis y la API Forgejo tiene pruebas unitarias.
No se han ejecutado en cuentas remotas ni se han configurado tokens o runners.
