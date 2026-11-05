# Evidencia de validación — 51.1~ynh5

Validado el 5 de noviembre de 2026 en Debian 12 / YunoHost 12.1.41.2 / amd64.

| Prueba | Resultado |
| --- | --- |
| Esquemas, ShellCheck, Bash/Python y YAML GitHub/Forgejo | Correctos |
| Unitarias: RS256/RS512, claims, claves, política y configuración | 49 correctas en el entorno local y otras 49 en Debian 12; sin omisiones |
| OIDC HTTPS con firmas RS256 reales | 115 comprobaciones correctas, incluida restauración |
| OIDC HTTPS con firmas RS512 reales | 115 comprobaciones correctas, incluida restauración |
| Rechazo de downgrade y algoritmos no seleccionados | Correcto |
| SSOwat/LDAP, perfiles, roles, revocación, TOTP y recuperación | 53 comprobaciones correctas, incluida restauración |
| MariaDB nativa, migraciones, documentos y limpieza de sesiones parciales | Correcto |
| Contraseñas/tokens ausentes de los registros comprobados | Correcto |
| package_check: linter, raíz, subruta, varias instancias, backup/restore, upgrade, change_url | 7 resultados originales `success` |
| SMTP STARTTLS y PDF tras restaurar, como usuario de servicio | Correctos; sin enviar correo de prueba; PDF de 4093 bytes |
| Plantillas de proveedores | Sintaxis JSON/YAML correcta; no se han activado cuentas cloud |

Ambas suites OIDC prueban PKCE S256, clientes basic/post/públicos, state y replay,
caducidad real, TOTP, elección de entrada nativa/OIDC y vínculos LDAP explícitos.
El proveedor de prueba es efímero con HTTPS y RSA 2048. No equivale a probar las
cuentas Google/GitHub/Microsoft ni a certificar un producto IdP concreto.

La **nota oficial permanece en 0**: `AppCatalog.is_in_catalog` es crítico y
`AppCatalog.state_is_working` es error. Los avisos restantes son README manual y
categoría. El wrapper conserva ese resultado; no convierte la ausencia en el
catálogo comunitario en una aprobación. Los siete escenarios funcionales pasan.

- `package-check-results.json` y `package-linter.json`: resultados originales.
- `oidc-tests.json`: RS256; `oidc-rs512-tests.json`: RS512.
- `sso-tests.json`: comprobaciones nativas LDAP.
- `provider-catalog.json`: consulta de disponibilidad YunoHost; no es una instalación.
- `environment.json` y `package-check-commit.txt`: entorno y revisiones utilizadas.
- `runtime.sha256`: hashes de los 23 archivos funcionales/configuración probados.
- `supplementary-tests.json`: comprobaciones adicionales y límites.

`asm3_ynh-51.1~ynh5-validation.tar.gz` contiene informes, logs y la instantánea previa
al informe final. Documentación y plantillas se completan después; los 23 archivos
funcionales coinciden con los de la matriz. Compruébalo con
`sha256sum -c doc/validation/runtime.sha256`.

No se han publicado repositorios remotos ni ejecutado sus workflows. La matriz no
se ha repetido sobre ARM. Claves privadas y discos del laboratorio quedan excluidos.
