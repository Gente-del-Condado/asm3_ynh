# Evidencia de validación

## Paquete 51.1~ynh10

Validación del 14 de noviembre de 2026 en Debian 12 / YunoHost 12.1.41.2 / amd64.
Los siete escenarios del [JSON original](package-check-51.1~ynh10.json) terminaron
con `success` sobre el commit `c7a29694fa5fa3b7b968663760a321e0a8543411`.
El nivel oficial permanece en 0 por los hallazgos de catálogo.

Pasaron 72 pruebas unitarias en local y otras 72 en Debian 12, además del smoke
test con MariaDB temporal. Las pruebas verifican INFO por stdout en mantenimiento,
advertencias y errores por stderr, conservación de diagnósticos desconocidos y
salida distinta de cero ante un fallo fatal o una migración fallida. Un fallo del
generador de esquema conserva su código de error. La generación del JavaScript
separa los datos y los mensajes de progreso.

La vista normal de YunoHost mostró las fases SQLite y MariaDB en español.
Los INFO internos aparecen traducidos en el registro detallado y desapareció el
aviso de retirada de una carpeta upstream inexistente. Los diagnósticos propios
de YunoHost, APT y MariaDB se conservan con su texto original.

- [Resultados de mensajes y errores](messages-51.1~ynh10.json).
- [Hashes de los archivos funcionales](runtime-51.1~ynh10.sha256).

## Paquete 51.1~ynh9

Validación del 12 de noviembre de 2026 en Debian 12 / YunoHost 12.1.41.2 / amd64.
El [JSON original](package-check-51.1~ynh9.json) registra siete escenarios correctos
sobre el commit `c261b5dc73fd08baa615333056181c87d8e26a2d`. El nivel oficial sigue en 0 por los hallazgos del catálogo.

Pasaron 70 pruebas unitarias en local y otras 70 en Debian 12, además del smoke
test con MariaDB temporal como usuario sin privilegios. La prueba de regresión
ejercita el módulo real de caché y verifica la invalidación de una entrada ausente,
el borrado repetido y el registro de un error de permisos. En los registros del
smoke test y de la matriz completa no aparece el falso `CRITICAL cachedisk.delete`.

- [Resultados de caché](cache-51.1~ynh9.json).
- [Hashes de los archivos funcionales](runtime-51.1~ynh9.sha256).

## Paquete 51.1~ynh8

Validación del 12 de noviembre de 2026 en Debian 12, YunoHost 12.1.41.2 y amd64.

- Los siete escenarios oficiales de [package_check](package-check-51.1~ynh8.json)
  terminaron con `success`. El nivel global permanece en 0 por los hallazgos del catálogo.
- Pasaron 70 pruebas unitarias en local y otras 70 en Debian 12.
- Pasó el smoke test con MariaDB temporal como usuario sin privilegios en Debian.
- En Chrome, el mapa de Opciones → Detalles del refugio cargó seis teselas reales
  de OpenStreetMap con HTTP 200. El Referer contenía solo el origen HTTPS ficticio.
- La respuesta de la página mantiene `strict-origin-when-cross-origin` y la
  pantalla MFA mantiene `no-referrer`.
- El PNG se sirvió desde el portal y su hash apareció en la API de administración.
  Un logo personalizado sobrevivió a una actualización completa.
  La restauración del predeterminado se comprobó retirando su PNG y recuperándolo.
- [Comprobaciones detalladas del mapa y del logo](mapa-logo-51.1~ynh8.json).
- [Captura del mapa con datos ficticios](mapa-51.1~ynh8.webp).

La matriz probó `aff1da328048449f2abc1ff01bb14d068f0a9bdb`.
Durante la publicación se aplicaron las correcciones al historial actualizado de
Forgejo. Se verificó que el árbol completo de fuentes de
`245b21e` coincide byte a byte con el probado. El JSON conserva la revisión
original de package_check. Los informes y esta documentación se añadieron después.

```bash
sha256sum -c doc/validation/runtime-51.1~ynh8.sha256
```

## Paquete 51.1~ynh7

La matriz completa del 7 de noviembre de 2026 probó el commit
`4f4d3b34869b168e593258021ddae98110f0cdc1`, clonado de Forgejo. Los siete
escenarios pasaron en Debian 12, YunoHost 12.1.41.2 y amd64. Incluyen una
actualización sobre la misma versión y un cambio de URL que duró 145 segundos.
El nivel global es 0 por los hallazgos de catálogo. Consulta el
[informe original](package-check-51.1~ynh7.json).

Los hashes y resultados que siguen corresponden a la versión anterior.
Compruébalos desde la revisión probada si necesitas reproducirlos.

## Paquete 51.1~ynh6

Validación del 5 de noviembre de 2026, Debian 12 / YunoHost 12.1.41.2 / amd64.

| Prueba | Resultado |
| --- | --- |
| Esquemas oficiales manifest/tests/config panel, ShellCheck, Bash/Python y YAML GitHub/Forgejo | Correctos |
| Unitarias, firmas, política, MFA, configuración y extracción segura | 66 correctas en el entorno local y otras 66 en Debian 12; sin omisiones |
| OIDC HTTPS con firmas RS256 reales | 127 comprobaciones correctas, incluida MFA y restauración |
| OIDC HTTPS con firmas RS512 reales | 127 comprobaciones correctas, incluida MFA y restauración |
| SSOwat/LDAP nativo, perfiles, roles, revocación, MFA y recuperación | 62 comprobaciones correctas, incluida restauración |
| Dex 2.46.1~ynh1 real, panel y MFA obligatorio | 50 comprobaciones correctas; LDAP completo y redirecciones OAuth Google/GitHub/Microsoft |
| MariaDB nativa, migraciones, documentos y sesiones parciales | Correctos en el host y Debian 12 |
| Auditoría de credenciales en registros actuales | Correcta; variantes literales, JSON, URL y shell, sin mostrar valores |
| package_check integral | 7 escenarios originales `success`, sin omisiones; cambio de URL ejecutado durante 143 segundos |
| SMTP STARTTLS como usuario del servicio | Correcto tras restaurar; sin enviar correo de prueba |
| PDF como usuario del servicio | Correcto, 7681 bytes |
| Pantalla MFA en navegador | QR cargado, etiquetas, POST, código de texto y teclado numérico; sin desbordamiento horizontal ni errores de consola |

Las pruebas Dex incluyen inscripción TOTP, CSRF, bloqueo persistente, rechazo de
códigos reutilizados entre navegadores, restablecimiento root y revocación de
sesiones y verificaciones pendientes. Se comprueban secretos con caracteres
especiales, campos de contraseña vacíos, fallo de discovery con reversión,
permisos de visitantes, conservación de un cliente ajeno, backup/remove/restore,
cambio de URL, hook y desconexión de Dex sin retirar la aplicación compartida.

Se comprobaron los endpoints y callbacks OAuth reales generados por los tres
conectores y `User.Read` en Microsoft Graph. **No se completaron logins con
cuentas cloud reales ni se crearon registros de clientes en sus consolas.** Los
conectores usan credenciales ficticias de laboratorio. Debes registrar tus propios
clientes y configurarlos desde el panel. El flujo LDAP de Dex sí se probó completo.

Ambas suites OIDC usan un proveedor efímero HTTPS con RSA 2048, PKCE, state,
nonce, replay, expiración, políticas, roles y vínculo LDAP explícito. Los helpers
del laboratorio completan el segundo factor; únicamente el harness root reinicia
su contador entre casos. La aplicación de producción nunca lo reinicia al entrar.
La suite Dex prueba replay y bloqueo sin ese ajuste.

El linter oficial, conservado también en un recheck JSON del commit exacto tras
la limpieza automática de sus temporales, conserva `AppCatalog.is_in_catalog` como crítico y
`AppCatalog.state_is_working` como error: el paquete aún no está en el catálogo
comunitario. También avisa del README manual y de la categoría. El wrapper no
falsea esos hallazgos ni convierte el nivel oficial 0 en una aprobación de calidad.

- `package-check-results.json` y `package-linter.json`: resultados originales.
- `oidc-tests.json`, `oidc-rs512-tests.json`, `sso-tests.json`, `dex-tests.json`: casos y resultados.
- `environment.json` y `package-check-commit.txt`: entorno y revisiones utilizadas.
- `runtime.sha256`: hashes de los 31 archivos funcionales/configuración de la matriz.
- `test-tools.sha256`: hashes de herramientas, suites, esquemas y workflows.
- `supplementary-tests.json`: comprobaciones adicionales y límites.
- `provider-catalog.json`: consulta previa del catálogo; no equivale a desplegar todos los IdP.

El archivo `asm3_ynh-51.1~ynh6-validation.tar.gz` contiene la matriz completa,
con informes, logs y la instantánea anterior a los informes finales. Los hashes
permiten comprobar que añadir documentación e informes no cambia el código probado:

```bash
sha256sum -c doc/validation/runtime.sha256
sha256sum -c doc/validation/test-tools.sha256
```

La vista del navegador emplea una cuenta y semilla ficticias en loopback y el HTML
del módulo entregado; no es una sesión real ni una prueba de viewport móvil.
No se ha probado ARM ni se han ejecutado workflows remotos o publicado forjas.
Discos, claves privadas, bases de datos y credenciales del laboratorio se excluyen
por completo del Git y de los artefactos de distribución.
