# Evidencia de validación — 51.1~ynh4

Validado el 5 de noviembre de 2026 en Debian 12 / YunoHost 12.1.41.2 / amd64.

| Prueba | Resultado |
| --- | --- |
| Esquemas, ShellCheck, Bash/Python y YAML GitHub/Forgejo | Correctos |
| Unitarias, incluidas firma/claims/política/configuración OIDC | 35 correctas tanto en el entorno local como en Debian 12; sin omisiones |
| OIDC real: proveedor HTTPS efímero, RS256 y PKCE | 115 comprobaciones correctas |
| SSOwat/LDAP reales: perfiles, roles, revocación, TOTP, logout y recuperación | 53 comprobaciones correctas |
| Copia, eliminación y restauración con OIDC activado | Correcto; conserva configuración, CA, identidad y roles |
| Copia, eliminación y restauración de perfiles LDAP | Correcto; conserva UUID y roles |
| MariaDB nativa: instalación, login, migraciones y documentos | Correcto |
| Regresión de sesión parcialmente inicializada tras fallo de autorización | Correcto; borra usuario/privilegios y rota el identificador |
| Contraseñas, tokens, debug de correo y diagnósticos 500 | Correcto; secretos ausentes en los destinos comprobados |
| package_check: linter, raíz, subruta, varias instancias, backup/restore, upgrade y change_url | 7 resultados originales `success` |
| SMTP con STARTTLS tras restaurar, como usuario de servicio | Correcto; sin enviar correo de prueba |
| PDF tras restaurar, como usuario de servicio | Correcto; 4222 bytes |

OIDC se ha probado con `client_secret_basic`, `client_secret_post` y clientes
públicos `none`, siempre con PKCE. Incluye expiración real de sesión, rechazo de
state/cookie/replay y tokens inválidos, TOTP, separación de cuentas con nombre/correo
coincidente, selección entre portal/OIDC y revocación LDAP de vínculos explícitos.
El proveedor es una fixture local HTTPS que firma tokens auténticos; no se afirma
certificación ni ejecución de estas pruebas contra todos los IdP comerciales.

La **nota oficial es 0**. El linter marca `AppCatalog.is_in_catalog` como crítico
y `AppCatalog.state_is_working` como error: la aplicación no está aceptada en el
catálogo comunitario. Los avisos restantes son README manual y categoría.
El wrapper conserva ese resultado y devuelve error de calidad, aunque los siete
escenarios funcionales pasen. La instalación personalizada no requiere alta editorial.

- `package-check-results.json`: JSON original de la matriz final.
- `package-linter.json`: JSON original del linter.
- `oidc-tests.json` y `sso-tests.json`: comprobaciones integradas, sin secretos.
- `supplementary-tests.json`: unitarias, MariaDB, SMTP, PDF y estado de las forjas.
- `environment.json`: versiones, imágenes y commit exacto de la matriz.
- `runtime.sha256`: hashes de los 23 archivos funcionales/configuración probados.
- `package-check-commit.txt`: revisión de la herramienta oficial.

`asm3_ynh-51.1~ynh4-validation.tar.gz` contiene informes y logs completos. La
instantánea anterior a los informes identifica el código de la matriz; los scripts
de pruebas y documentación se completan después. Los 23 archivos funcionales de
la entrega coinciden con los probados: `sha256sum -c doc/validation/runtime.sha256`.

No se han publicado repositorios remotos ni ejecutado los workflows en cuentas
GitHub/Forgejo. No se ha repetido la matriz sobre ARM. Discos, claves privadas,
configuraciones activas y credenciales del laboratorio quedan fuera del repositorio.
