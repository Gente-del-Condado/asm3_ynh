# Estudio de integración

Revisión realizada el 5 de noviembre de 2026 contra fuentes públicas oficiales.

| Fuente | Hallazgo | Decisión del paquete |
| --- | --- | --- |
| [sheltermanager/asm3](https://github.com/sheltermanager/asm3) | Aplicación Python, web.py incluido, interfaz WSGI; admite MySQL/MariaDB, PostgreSQL y SQLite | Python del sistema, WSGI/Cheroot y MariaDB gestionada por YunoHost |
| [Última publicación estable](https://github.com/sheltermanager/asm3/releases/tag/51-1) | 51-1; corrige la creación de salesreceipt en bases nuevas de 51 | Fuente de 51-1 por commit inmutable y SHA-256 |
| Rama master, archivo VERSION | Marca 52u en el momento de la revisión | El seguimiento diario selecciona releases estables, no commits de desarrollo |
| [jon-donker/asm3_docker](https://github.com/jon-donker/asm3_docker) | Dockerfile descarga sheltermanager3_49_all.deb; Apache/mod_wsgi, Ubuntu 24.04 y PostgreSQL 16; README reconoce redirecciones pendientes | Integración nativa y URL pública explícita, sin encadenar Apache y Nginx |
| [Ejemplo oficial de YunoHost](https://github.com/YunoHost/example_ynh) | Formato 2, helpers 2.1, recursos declarativos y scripts de ciclo de vida | Aprovisionamiento/deprovisión por el gestor de recursos |
| [Helpers oficiales](https://github.com/YunoHost/yunohost/tree/dev/helpers/helpers.v2.1.d) | Helpers de fuente verificada, base de datos, Nginx, systemd y copias | Reutilización de helpers, sin crear bases ni usuarios manualmente en scripts de instalación |

## Adaptaciones

La URL pública configura `base_url` y `service_url`. Nginx elimina el prefijo antes
de pasar las peticiones al puerto de loopback. El adaptador WSGI establece
`SCRIPT_NAME`, HTTPS y la dirección del cliente, y usa el middleware estático que
ya incluye upstream. Así se mantienen las rutas de la aplicación y de sus recursos.

ASM3 utiliza de origen los mismos nombres de cookies y Path=/ en cada instalación.
El adaptador cambia los nombres al entrar/salir del proceso y los limita a la ruta
de la instancia, evitando interferencias entre instalaciones en un mismo dominio.

El archivo GitHub de código fuente no incluye `asm3/__version__.py` ni el esquema
estático del editor SQL. Se generan localmente siguiendo las herramientas de
upstream. La interfaz utiliza los JavaScript originales (`rollup_js=false`), de modo
que no requiere Node/npm ni descargar una cadena de compilación en el servidor.

Los informes predeterminados se generan desde los `.rep` del mismo archivo
verificado. La instalación no necesita contactar con el catálogo externo de
informes. Durante el uso normal ASM3 conserva su acceso al catálogo oficial.

El parche `patches/main/0001-mysqlclient-escape-string.patch` importa la función
`escape_string` desde el módulo nativo `MySQLdb._mysql`: las versiones modernas de
mysqlclient no la exportan en el nivel superior que utiliza ASM3 51-1. Los helpers
de YunoHost aplican el parche después de comprobar el archivo original; el smoke
test aplica exactamente el mismo parche y falla si deja de ser compatible.

Las pruebas detectaron dos defectos de las plantillas de formularios de 51-1:

- `onlineformfield.Label` es VARCHAR(255), pero la solicitud de adopción incluye un
  texto más largo. Se amplía a TEXT antes de importar, manteniendo el modo estricto
  de MariaDB y el texto íntegro.
- `rspca_510_observations_dog.json` repite `reaction`. La segunda aparición recibe
  un sufijo numérico. Se comprueba el número de campos importados de cada archivo y
  se propaga cualquier fallo; no se acepta silenciosamente un formulario parcial.

Las cuentas de ejemplo se deshabilitan y sus contraseñas se aleatorizan. El
administrador elegido se vincula explícitamente a LDAP. Una cuenta local separada
permite recuperación; su secreto generado entra en la inicialización por stdin.

El idioma elegido se guarda también como `Locale` en la tabla `configuration`.
ASM3 mezcla sus valores predeterminados al leer esa tabla, por lo que únicamente
escribir `locale=es` en el archivo no basta para que la interfaz aparezca en español.
La actualización repara instalaciones sin ese registro y respeta preferencias ya
guardadas por el usuario. La prueba HTTP exige el título de acceso en español.

Los documentos permanecen en el almacenamiento de base de datos de ASM3. Esto
permite una copia SQL transaccional que incluye registros y documentos, también
durante las copias previas a actualizar. El directorio de datos solo contiene caché
y el archivo de bloqueo. Las tareas por lotes y el mantenimiento comparten bloqueo.

## Límites de integración

La identidad SSO procede de SSOwat y se valida en LDAP. El permiso `staff`
autoriza el acceso privado y los roles de ASM3 determinan las operaciones.
Consulta [SSO.md](SSO.md) para el diseño y la recuperación. El uso de publicadores, cobros, S3 y otros servicios
externos requiere sus respectivas credenciales; el paquete incluye sus dependencias
Python, pero no puede crear cuentas ni validar servicios externos sin ellas.

El seguimiento diario genera paquetes y propuestas de actualización en GitHub.
El administrador aplica las actualizaciones con YunoHost. El catálogo comunitario
y sus niveles de calidad requieren publicación, pruebas y revisión independientes.
