# Evidencia de validación — 51.1~ynh3

Validado el 5 de noviembre de 2026 en Debian 12 / YunoHost 12.1.41.2 / amd64.

| Prueba | Resultado |
| --- | --- |
| Esquemas, ShellCheck, Bash/Python y YAML de GitHub/Forgejo | Correctos |
| Unitarias de proxy, LDAP, actualizador y Forgejo | 16 correctas |
| MariaDB nativa: instalación, login, migraciones y documentos | Correcto |
| Regresión de secretos: login/API/base64, debug de correo y respuesta/diagnóstico 500 | Correcto |
| SSOwat/LDAP reales: perfiles, permisos, roles, revocación, TOTP, logout y recuperación | 53 comprobaciones correctas, incluidas restauración y cambio de identidad |
| package_check: linter, raíz, subruta, varias instancias, backup/restore, upgrade y change_url | 7 resultados originales `success` |
| SMTP autenticado con STARTTLS tras restaurar, como usuario de servicio | Correcto; sin enviar correo de prueba |
| PDF tras restaurar, como usuario de servicio | Correcto; 4488 bytes |

La **nota oficial es 0**. El linter marca `AppCatalog.is_in_catalog` como crítico
y `AppCatalog.state_is_working` como error: la aplicación no ha sido aceptada en
el catálogo comunitario. Sus avisos restantes son README manual y categoría.
No se modifican esos criterios ni se presenta el wrapper como aprobado: devuelve
error de calidad pese a los siete escenarios funcionales correctos.
La instalación personalizada desde un repositorio no requiere alta en el catálogo.

- `package-check-results.json`: JSON original de la matriz final.
- `package-linter.json`: JSON original del escenario linter, con duración y resultado.
- `sso-tests.json`: las 53 comprobaciones integradas, sin secretos.
- `supplementary-tests.json`: pruebas nativas, SMTP, PDF y estado de las forjas.
- `environment.json`: versiones, imágenes y commit exacto sometido a la matriz.
- `runtime.sha256`: hashes de los 20 archivos funcionales/configuración probados.
- `package-check-commit.txt`: revisión de la herramienta oficial.

El archivo `asm3_ynh-51.1~ynh3-validation.tar.gz` incluye estos informes, el log
completo oficial, los logs nativo/unitario/SSO y el paquete exacto anterior a añadir
los informes finales. Los archivos funcionales de la entrega coinciden con los de
ese paquete; compruébalo con `sha256sum -c doc/validation/runtime.sha256`.

No se han publicado repositorios remotos ni ejecutado los workflows en cuentas
GitHub/Forgejo. La matriz no se ha repetido en ARM. El laboratorio y sus claves
privadas quedan fuera de Git y de los archivos de entrega.
