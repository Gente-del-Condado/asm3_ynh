# SSO nativo de YunoHost y LDAP

Desde `51.1~ynh3`, el portal autentica al usuario y SSOwat suministra `YNH_USER`.
Nginx sobrescribe las cabeceras del cliente y añade un secreto por instancia.
Cheroot rechaza peticiones directas sin ese secreto, incluso desde loopback.
El archivo Nginx es root:root 0600 y la configuración de ASM3 root:app 0640.
La cabecera Authorization del portal se elimina antes de llegar a ASM3.
No se realiza bind LDAP con la contraseña del usuario ni se copia su contraseña.
La lectura LDAP anónima local usa filtros escapados, tiempos máximos y sin referrals.

## Permisos y perfiles

- `asm3.main`: quién puede alcanzar la aplicación, incluidos sus servicios públicos.
- `asm3.staff`: quién puede utilizar SSO privado. Inicialmente `all_users`; restringe
  este permiso en Usuarios → Grupos y permisos si solo parte del servidor es personal.
- Roles ASM3: qué puede hacer cada perfil. Nuevos perfiles: `YunoHost (read only)`,
  permiso `va` de lectura de animales, sin superusuario. Amplía los roles en ASM3.
- El administrador elegido al instalar conserva el perfil administrador ID 1.

Autorizar visitantes en `main` no autoriza personal en `staff`. El permiso staff
protege `/ynh_sso`; la aplicación vuelve a comprobarlo en LDAP en cada solicitud
privada autenticada, incluso si se entra por otra URL. No hay caché de concesiones.
La baja del usuario, la revocación del permiso o DisableLogin en ASM3 bloquean la
siguiente solicitud privada. Los cambios de roles se recargan también por solicitud.
Si LDAP no está disponible, el acceso SSO se deniega; la recuperación local sigue disponible.

Cada perfil se vincula a `entryUUID`. Recrear un nombre no hereda los datos del
perfil anterior. Una colisión con un usuario local se rechaza; no se fusionan
cuentas automáticamente. Nombre completo y correo se sincronizan desde LDAP;
los roles, ubicación, filtros y preferencias se conservan en ASM3.
Si se cambia el UID en LDAP, se conserva el identificador interno previo de ASM3.
Los perfiles deshabilitados no se reactivan automáticamente.

Ejemplo de restricción desde la CLI YunoHost 12:

```bash
sudo yunohost user permission add asm3.staff alice bob
sudo yunohost user permission remove asm3.staff all_users
```

En instalaciones múltiples sustituye `asm3` por el identificador, por ejemplo `asm3__2`.

## 2FA y cierre de sesión

Desde `51.1~ynh6`, el paquete exige TOTP a todos los accesos privados, con independencia
de Force2FA. Después de verificar el primer factor se retiran de la sesión usuario,
roles y base de datos hasta confirmar el código. El alta se completa con un primer
código válido; un factor existente se reutiliza. QR y clave manual solo se muestran
durante el alta, con `no-store`, CSRF y CSP. El código no puede reutilizarse y cinco
fallos bloquean la cuenta cinco minutos. La comprobación pendiente caduca en cinco
minutos y la sesión MFA en ocho horas como máximo (OIDC además limita por su token).

Restablece un factor perdido desde el panel YunoHost, sección recuperación,
indicando el nombre exacto de usuario ASM3. Esta acción root invalida tanto sesiones
abiertas como verificaciones pendientes; nunca crea una excepción al segundo factor.
La recuperación de contraseña conserva el factor. Los perfiles no usan remember-me.

Salir de ASM3 destruye su sesión y muestra la pantalla de acceso sin reconectar
inmediatamente. La sesión del portal permanece abierta: volver a `/ynh_sso` o a
la raíz de la aplicación permite entrar otra vez. Para salir de todas las
aplicaciones, cierra también la sesión del portal YunoHost. Al faltar la identidad
SSOwat se elimina la sesión SSO de ASM3 en la siguiente solicitud privada.

## Recuperación y cuentas de servicio

La cuenta local `ynh_rescue_asm3` tiene privilegios administrativos y un secreto
aleatorio generado por el paquete. Obtén el secreto solo en una terminal root:

```bash
sudo yunohost app setting asm3 rescue_password
```

Entra por `https://DOMINIO/RUTA/login?local=1`. Los permisos de acceso de YunoHost
siguen aplicándose: en caso de avería del portal, un administrador del servidor
puede permitir temporalmente visitantes en main y usar ese formulario.
La cuenta de recuperación no utiliza LDAP ni recibe privilegios del portal.
Si cambias su contraseña en ASM3, el valor inicial guardado por YunoHost deja de
ser válido; consérvalo en tu gestor de secretos. No se resetea en las actualizaciones.

Las API autenticadas por contraseña se bloquean para todas las cuentas, incluidas
las de servicio, porque omitirían el segundo factor. Los servicios públicos,
formularios y callbacks de pagos conservan el comportamiento de ASM3.
Usa POST para credenciales. Se desactiva access_log en la ubicación ASM3 para no
registrar contraseñas enviadas por clientes antiguos en la query; los logs de ASM3
no imprimen contraseñas fallidas, datos base64 ni códigos TOTP. También se
omite el cuerpo de los correos del debug y se excluyen datos de petición, cookies
y configuración de las páginas y correos de error interno. Evita incluir
secretos en URL: los navegadores y proxies externos pueden guardarlas.

## Actualización desde ~ynh2 y restauración

Al actualizar, el administrador seleccionado y guardado por YunoHost se vincula
explícitamente al perfil ID 1. Su contraseña local anterior se invalida y se crea
la cuenta de recuperación. Los demás perfiles locales se conservan. Si un usuario
LDAP coincide con uno local, la provisión se bloquea para evitar apropiación; un
administrador debe resolver el conflicto antes de incorporar ese usuario al SSO.
Si el administrador inicial fue renombrado en ASM3, la migración se detiene y
YunoHost conserva la copia previa; no se adivina qué cuenta elevar a administrador.

La copia SQL incluye perfiles, roles y las tablas `ynh_auth_identity` y
`ynh_auth_config`. La copia de YunoHost incluye los secretos y la configuración.
La restauración conserva las vinculaciones y permisos. Si se restaura en otro
servidor cuyo LDAP tiene UUID diferentes, no se enlazan por nombre: requiere
una migración explícita, usando primero el administrador de recuperación.

Desde `51.1~ynh4` también hay un cliente OpenID Connect opcional, sin sustituir
este SSO nativo ni LDAP. Consulta [OIDC.md](OIDC.md). El paquete no instala un IdP.
