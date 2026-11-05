Abre https://__DOMAIN____PATH__ desde el portal YunoHost como **__ADMIN__**.
El SSO crea perfiles desde LDAP. El personal nuevo recibe solo lectura de animales;
asigna otros roles en ASM3. El administrador elegido tiene acceso completo.

Limita el permiso **staff** al personal. Para adopciones, formularios y API públicos,
permite visitantes en **main** y configura los servicios de ASM3.

Recuperación local: `/login?local=1`, usuario `ynh_rescue___APP__`.
Como root, consulta la contraseña con `yunohost app setting __APP__ rescue_password`.
No la compartas ni la incluyas en registros. Las cuentas de ejemplo están deshabilitadas.

Configura organización, zona horaria y correo en ASM3. El SMTP local ya está configurado.

OpenID Connect opcional: configura un cliente registrado siguiendo `doc/OIDC.md`. El SSO nativo permanece disponible.

TOTP es obligatorio en todos los accesos privados. Inscribe el factor al entrar.
Google/GitHub/Microsoft: instala Dex y configura sus clientes en el panel de ASM3
de YunoHost. El mismo panel permite restablecer un factor perdido. Guía: `doc/DEX.md`.
