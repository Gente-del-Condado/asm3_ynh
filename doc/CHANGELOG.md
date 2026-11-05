# Cambios del paquete

## 51.1~ynh3 — 5 de noviembre de 2026

- SSO nativo SSOwat con autorización LDAP por permiso staff y perfiles automáticos.
- Identidades vinculadas por entryUUID, perfiles iniciales de solo lectura y roles conservados.
- Administrador de recuperación local generado y migración del administrador existente.
- Se conserva la comprobación TOTP de ASM3 y se invalida la sesión al revocar LDAP.
- Se eliminan contraseñas y códigos 2FA de los logs de autenticación y recuperación.
- Se excluyen cuerpos de correo del debug y secretos de los diagnósticos 500.
- Pruebas de límites de confianza y suite integrada para un YunoHost desechable.


## 51.1~ynh2 — 5 de noviembre de 2026

- Persistencia del idioma inicial en la configuración de ASM3 y reparación de
  instalaciones que no lo guardaron, respetando las preferencias existentes.
- Comprobaciones HTTP de la página de acceso en español y del esquema JavaScript.
- Requisitos de disco ajustados a 2 GiB para incluir las dependencias completas.
- CI y seguimiento de nuevas publicaciones para GitHub y Forgejo.
- Ejecutor de `package_check` con snapshot Git limpio, compatibilidad con los alias
  actuales de imágenes YunoHost y conservación de resultados y logs.
- Smoke test compatible con jobs desechables ejecutados como root.
- SMTP autenticado con STARTTLS en el puerto de envío 587 de YunoHost.

## 51.1~ynh1

- Primera adaptación nativa de ASM3 51-1 a YunoHost, con MariaDB, Nginx y systemd.
- Instalación, actualización, cambio de URL, eliminación, copias y restauración.
- Cuentas predeterminadas deshabilitadas y cookies independientes por instancia.
- Correcciones de formularios incluidos y compatibilidad con mysqlclient moderno.
