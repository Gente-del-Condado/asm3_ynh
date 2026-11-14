# Administrar Animal Shelter Manager

Consulta el [manual web de ASM3 para YunoHost](https://gente-del-condado.github.io/asm3_ynh/) para ver los pasos de instalación, ejemplos y capturas.

## Primer día

- Abre https://__DOMAIN____PATH__ desde el portal YunoHost con **__ADMIN__**.
- Configura TOTP en el primer acceso. Los perfiles nuevos de LDAP empiezan con
  permiso de lectura de animales. Asigna los roles necesarios desde ASM3.
- Configura la organización, la zona horaria, el remitente y los informes.
- Si ofreces formularios de adopción o servicios públicos, habilita visitantes
  en el permiso `main` y configura cada servicio en ASM3. Restringe el permiso
  `staff` al personal. Prueba ambos accesos desde una ventana privada.

## Copias y actualizaciones

Haz la copia desde el panel de YunoHost o con `sudo yunohost backup create --apps __APP__`.
Conserva una copia fuera del servidor y prueba restaurarla en un entorno separado.
La copia incluye registros, configuración, documentos e imágenes. Los archivos
persistentes se guardan en MariaDB, por lo que debes conservar
`dbfs_store = database`. La caché se vuelve a crear en la restauración.

Actualiza desde YunoHost para aplicar migraciones y conservar la copia de
seguridad automática. Las plantillas de Nginx, systemd y ASM3 se regeneran en
actualizaciones o cambios de URL. Guarda las preferencias funcionales en ASM3.
Tras cambiar la URL, comprueba el acceso, los formularios y los callbacks
registrados en los proveedores externos.

## Identidad y recuperación

- [SSO nativo y LDAP](SSO.md) para el acceso desde el portal.
- [Dex](DEX.md) para Google, GitHub y Microsoft y [OIDC](OIDC.md) para proveedores externos con RS256 o RS512.
- El panel de ASM3 en YunoHost permite restablecer un TOTP perdido. La operación
  invalida las sesiones. La cuenta local de emergencia se usa en
  `/login?local=1`, con el nombre `ynh_rescue___APP__` y TOTP.
- Para consultar la contraseña de emergencia, usa como root
  `yunohost app setting __APP__ rescue_password` en una terminal privada.
  Evita copiar su salida a registros, incidencias o capturas.

## Diagnóstico

```bash
sudo systemctl status __APP__
sudo journalctl -u __APP__ -n 60 --no-pager
```

| Síntoma | Comprobación |
| --- | --- |
| 502 | Estado del servicio, journal y error de Nginx del dominio |
| Redirección al portal | Dominio y ruta, sesión SSOwat, permisos `main` y `staff` |
| Código TOTP rechazado | Hora del móvil y servidor, factor correcto, posible reutilización del código |
| Correo sin entregar | Diagnóstico de correo de YunoHost y DNS del dominio. ASM3 usa SMTP local con STARTTLS |
| Problemas tras actualizar | Registro de la operación y copia automática previa. Revisa que documentos y permisos se conserven |

El código se instala en `__INSTALL_DIR__/upstream`, el adaptador en
`__INSTALL_DIR__/ynh` y la caché en `__DATA_DIR__/cache`. El puerto local puede
consultarse con `yunohost app setting __APP__ port`. Una petición desde el servidor
a `http://127.0.0.1:PUERTO/_ynh_health` debe responder `ready`.

Las tareas diarias se lanzan a las 03:17 y los informes por correo al minuto 23 de
cada hora, según el reloj del servidor. Consulta [Home Assistant](HOME_ASSISTANT.md)
si quieres añadir una comprobación externa de disponibilidad.

## Mapa y logo

Desde `51.1~ynh8`, el mapa identifica el origen HTTPS del refugio ante
OpenStreetMap. Las peticiones de teselas no incluyen la ruta ni los parámetros
de las páginas privadas. Si aparece un 403 con el aviso de política de uso,
actualiza el paquete y recarga la página para que el navegador aplique la
nueva política. Un bloqueo de red o del proveedor puede requerir revisión adicional.

El logo de ASM3 se asigna al instalar o actualizar si la instancia no tiene uno.
Puedes elegir otro en el apartado de mosaicos y permisos de YunoHost. Las
actualizaciones conservan ese logo personalizado.

## Mensajes durante la instalación

Desde `51.1~ynh10`, la preparación y el mantenimiento de ASM3 muestran sus
mensajes en español. Primero aparece «Preparando el esquema SQLite temporal del
editor SQL de ASM3…». Después se prepara la base MariaDB de la instancia y se
cargan datos, plantillas, formularios e informes.

Los mensajes `INFO` del mantenimiento salen por stdout. Las advertencias y errores
salen por stderr, con sus detalles de diagnóstico y sus códigos de salida. La
generación del JavaScript del editor SQL conserva su salida separada de los mensajes.

YunoHost, APT y MariaDB generan sus propios mensajes según el idioma del sistema.
Por ejemplo, `/var/lib/mysql: found previous version 10.11` informa de la versión
detectada en su directorio. No se traducen mediante filtros de texto. Desde
`51.1~ynh9`, invalidar una entrada de caché inexistente tampoco genera un falso
`CRITICAL cachedisk.delete`.
