# OpenID Connect, SSO nativo y LDAP

Desde `51.1~ynh4`, ASM3 puede actuar como cliente OpenID Connect de un proveedor
externo, además del SSO nativo de YunoHost. OIDC está **desactivado por defecto**.
No se instala ni se sustituye el proveedor de identidad. Registra un cliente en tu
Dex, Keycloak, Authentik u otro proveedor que ofrezca discovery, Authorization Code,
PKCE S256 y tokens ID firmados con RS256 o RS512, según la selección del cliente. Se configura un emisor por instancia.
Las pruebas de entrega usan un proveedor HTTPS efímero con firma RSA real; no son
una certificación de interoperabilidad con cada producto comercial.

## Registrar el cliente

Para una instalación `https://refugio.example.org/asm3`:

| Campo | Valor |
| --- | --- |
| URL de entrada de la aplicación | `https://refugio.example.org/asm3/oidc/login` |
| Redirect URI exacta | `https://refugio.example.org/asm3/oidc/callback` |
| Post-logout redirect URI | `https://refugio.example.org/asm3/oidc/logged_out` |
| Flujo | Authorization Code con PKCE S256, respuesta por query GET |
| Algoritmo del ID token | RS256 (predeterminado) o RS512, seleccionado explícitamente |
| Scopes iniciales | `openid profile email`; añade el scope de grupos si tu proveedor lo requiere |

En raíz de dominio omite `/asm3`; respeta exactamente dominio y ruta, sin comodines.
Tras cambiar la URL en YunoHost, actualiza también las URI registradas en el proveedor.
Un flujo iniciado con la URL anterior no se acepta en la nueva.

Si los usuarios OIDC no tienen sesión en YunoHost, permite visitantes en `asm3.main`
para que alcancen el inicio y el callback. Esto no los autoriza dentro de ASM3:
la política OIDC sigue siendo obligatoria. Mantén `asm3.staff` limitado al personal
para el acceso por SSO nativo y las vinculaciones LDAP.

## Configurar sin poner secretos en comandos

La instalación crea `/var/www/asm3/oidc.json`, propiedad root:asm3 y modo 0640.
La ruta real es el recurso `install_dir`, consultable con
`sudo yunohost app setting asm3 install_dir`.
La cuenta del servicio solo necesita leer este archivo; las credenciales no se
incluyen en argumentos, informes, tokens de navegador ni registros de diagnóstico.

Prepara un archivo root 0600, por ejemplo `/root/asm3-oidc.json`, con este contenido,
sustituyendo el emisor, cliente, secreto y sujetos/grupos permitidos:

```json
{
  "enabled": true,
  "issuer": "https://identidad.example.org",
  "client_id": "asm3",
  "client_secret": "SECRETO_DEL_CLIENTE_REGISTRADO",
  "id_token_signing_alg": "RS256",
  "token_endpoint_auth_method": "client_secret_basic",
  "scopes": ["openid", "profile", "email", "groups"],
  "allowed_subjects": [],
  "allowed_groups": ["personal-refugio"],
  "groups_claim": "groups",
  "ldap_links": {},
  "session_max_age": 3600
}
```

Aplica el archivo con el configurador instalado:

```bash
sudo python3 /var/www/asm3/ynh/manage_oidc.py --app asm3 --config /root/asm3-oidc.json --validate-only
sudo python3 /var/www/asm3/ynh/manage_oidc.py --app asm3 --config /root/asm3-oidc.json
```

El configurador valida JSON y discovery con TLS, escribe de forma atómica, fija
permisos y espera que el servicio responda. Si falla el reinicio, restaura el archivo
previo. Discovery no puede comprobar por sí solo que el proveedor haya registrado
correctamente tu secreto o las URI: el primer login completa esa comprobación.
No imprime secretos ni el contenido de los errores del proveedor.
Conserva el archivo fuente en un lugar protegido o elimínalo después de configurarlo.

Se admiten `client_secret_basic`, `client_secret_post` y `none` para clientes
públicos registrados con PKCE. No añadas un secreto cuando uses `none`.
El nombre de la clave JSON `groups_claim` permite elegir un claim de nivel superior;
su valor debe ser una lista de cadenas en el ID token firmado, no una cadena ni
un objeto anidado. `allowed_subjects` contiene valores `sub`, nunca nombres ni correos.
Se permite el acceso si coincide un sujeto **o** uno de los grupos permitidos.
Ambas listas vacías deniegan todos los accesos OIDC.

Para una CA privada, añade `"ca_bundle": "/var/www/asm3/oidc-ca.pem"`, instala el
certificado PEM root:asm3 0640 y conserva ese archivo en la copia. No se admite
TLS sin verificar, HTTP, redirecciones de backchannel ni credenciales en URL.

## Seleccionar RS256 o RS512

Configura `"id_token_signing_alg": "RS512"` si el proveedor anuncia RS512 y firma
así los ID tokens de este cliente. Sin esa propiedad se conserva RS256 para
compatibilidad. Se acepta exclusivamente el algoritmo seleccionado; no hay
negociación automática ni confianza en el algoritmo que indique un token recibido.
El cambio invalida las sesiones por la huella de configuración. RS512 no cambia
PKCE S256 ni convierte una clave RSA en una clave de 512 bits: el mínimo sigue en
2048 bits. Dex con su firmante local sigue requiriendo RS256.

Consulta [proveedores, MFA y accesos sociales](IDENTITY_PROVIDERS.md), con plantillas
para Google, GitHub y Microsoft mediante Dex y alternativas para YunoHost.

## Perfiles y vinculación con LDAP

La identidad es el par **emisor + sub**. El identificador interno es un hash de
ese par, con prefijo `oidc_`. Un perfil nuevo recibe el rol de lectura de animales,
sin superusuario. Asigna sus demás roles desde ASM3: no se elevan por llamarse
`admin`, por coincidir el correo ni por pertenecer a un grupo llamado administrador.
Los roles, ubicación y preferencias existentes se conservan. Nombre y correo se
sincronizan desde el token, y el correo solo se utiliza si `email_verified` es true.

Para que un sujeto OIDC concreto use su perfil YunoHost existente, configura una
vinculación explícita, controlada por root:

```json
"ldap_links": {
  "SUB_EXACTO_DEL_PROVEEDOR": "alice"
}
```

El sujeto debe superar igualmente la lista de autorización OIDC. Además, `alice`
debe existir y mantener el permiso LDAP `asm3.staff`. La vinculación guarda su
`entryUUID`: recrear el nombre con otro UUID no hereda el perfil. La revocación LDAP
bloquea también esa sesión OIDC en la siguiente solicitud privada. Los roles del
perfil LDAP son los de ASM3, incluidos los del administrador si lo has vinculado
expresamente. No añadas vinculaciones para sujetos que no hayas verificado.

No se reasigna una identidad ya creada a otro perfil al cambiar `ldap_links`.
Tampoco se permite reclamar un perfil local por nombre o vincularlo a un segundo
sujeto OIDC. Si necesitas migrar vínculos existentes, realiza una migración explícita
con copia previa; el paquete deniega la fusión automática.
Con Dex usando LDAP, obtiene el `sub` emitido por Dex: no asumas que es el UID ni
el UUID LDAP sin transformar. Su configuración y conectores corresponden al IdP.

## Entradas y sesiones

- SSO nativo: `/ynh_sso`, permanece disponible y comprueba LDAP.
- OpenID Connect: `/oidc/login`, que puedes usar en el acceso de tu proveedor o marcador.
- Recuperación local: `/login?local=1`, con `ynh_rescue_asm3`.

La entrada predeterminada sigue siendo el portal nativo. Un acceso explícito por
OIDC cambia a la identidad OIDC; volver a `/ynh_sso` cambia a la identidad LDAP.
Una cabecera del portal no sustituye una sesión OIDC seleccionada expresamente.
Las cuentas vinculadas a OIDC no aceptan contraseñas locales ni contraseñas por API.
Las integraciones API usan cuentas locales de servicio con permisos propios.

Se conserva el TOTP de ASM3: el token OIDC no permite saltarse un segundo factor
ya activado. La limitación de alta de TOTP para cuentas gestionadas descrita en
[SSO.md](SSO.md) sigue aplicándose.

El servidor valida la firma con las claves del proveedor, emisor, audiencia única,
`azp` si existe, caducidad, emisión, nonce y política de autorización. Cada transacción
usa state y verificador PKCE aleatorios, ligados a la sesión, de un solo uso y con
caducidad de cinco minutos. La cookie es HttpOnly, Secure y SameSite=Lax.
No se persisten tokens ID, access tokens ni refresh tokens. Solo se guarda en sesión
la identidad verificada y su plazo, limitado por `exp` y `session_max_age` (60–86400 s).
No se renueva la sesión mediante refresh tokens.

En cada solicitud privada se comprueban el estado y los roles ASM3 y la política
local actual. Cambiar o desactivar la configuración invalida las sesiones OIDC.
Los cambios de usuarios/grupos solo en el IdP se conocen en el siguiente login:
**no se implementan introspección ni logout backchannel/frontchannel**. Ajusta
`session_max_age` según el plazo de revocación que necesites. Para revocación inmediata,
deshabilita el perfil ASM3, cambia la lista local o utiliza una vinculación LDAP.

## Cierre de sesión, copias y desactivación

Salir por `/logout` destruye la sesión local de ASM3. `/oidc/logout` solicita también
el logout al proveedor si publica `end_session_endpoint`, con client_id y callback
fijo validado mediante state. No se envía el ID token en la URL. Los proveedores que
exijan `id_token_hint` adicional pueden requerir cerrar su sesión desde su portal.
Si el proveedor no ofrece logout o está caído, el cierre local sigue siendo efectivo.
No se cierra la sesión del portal YunoHost ni de otras aplicaciones automáticamente.

Las copias de YunoHost incluyen `oidc.json`, las CA guardadas dentro de install_dir,
los perfiles, roles y la tabla `ynh_oidc_identity`. Restaurar no cambia las identidades.
Comprueba las URI registradas si restauras en otro dominio. Las vinculaciones LDAP
requieren los mismos UUID o una migración explícita en el nuevo servidor.

Para desactivar OIDC, aplica un JSON con `"enabled": false` usando el mismo helper.
Los perfiles y vínculos se conservan; el SSO nativo y la recuperación siguen funcionando.

Referencias: [OpenID Connect Core](https://openid.net/specs/openid-connect-core-1_0.html),
[OAuth Security BCP](https://datatracker.ietf.org/doc/html/rfc9700),
[API PyJWT](https://pyjwt.readthedocs.io/en/stable/api.html),
[RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html)
y [conector LDAP de Dex](https://dexidp.io/docs/connectors/ldap/).
