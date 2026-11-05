# Proveedores de identidad, MFA y acceso social

Consulta del catálogo y documentación oficial: **5 de noviembre de 2026**.
La disponibilidad en YunoHost es distinta de que un producto implemente OIDC.
No se han desplegado estos proveedores ni creado clientes en cuentas externas.

## Opciones y disponibilidad

| Proveedor libre | Disponible como aplicación YunoHost consultada | MFA y uso propuesto |
| --- | --- | --- |
| Dex, Apache-2.0 | Sí: catálogo `working`, nivel 8 | Integra LDAP de YunoHost y federación Google/GitHub/Microsoft. El login LDAP de Dex no añade TOTP por sí mismo; exige MFA en el proveedor superior o en ASM3. |
| Pocket ID, BSD-2-Clause | Sí: catálogo `working`, nivel 7 | OIDC con passkeys, teléfono o llave de seguridad y verificación local. No es el flujo clásico contraseña + TOTP. Permite sincronizar usuarios/grupos LDAP; el usuario sigue autenticándose con passkey. |
| Authelia, Apache-2.0 | No figura como app en el catálogo consultado | OIDC con LDAP y MFA (TOTP/WebAuthn). Integrarlo como IdP separado requiere despliegue propio; no sustituir SSOwat ni añadir un segundo control global al proxy de YunoHost. |
| authentik, núcleo MIT con funciones Enterprise separadas | Figura en la lista de rechazadas, no como app soportada | Flujos de MFA TOTP/WebAuthn, LDAP y fuentes sociales. Buena opción como IdP externo para reunir varias identidades y exigir MFA después del acceso social. |
| Keycloak, Apache-2.0 | Figura en la lista de rechazadas, no como app soportada | LDAP, OTP/WebAuthn y federación social. Alternativa externa completa, con administración y recursos propios. |

La lista oficial rechaza Keycloak/authentik por su solapamiento con el SSO de
YunoHost. Esto no impide que ASM3 sea cliente OIDC de un IdP alojado en otra VM o
servidor. No se propone sobrescribir la autenticación nativa ni hacer pasar todo
YunoHost por un proxy de autenticación adicional.

**Elección práctica:** Pocket ID para passkeys y un despliegue sencillo dentro de
YunoHost; Dex para centralizar los tres accesos sociales y LDAP; un IdP externo
como authentik/Keycloak si necesitas una política MFA central y unificar varias
cuentas de la misma persona bajo una identidad estable.

Fuentes de disponibilidad: [catálogo oficial](https://github.com/YunoHost/apps/blob/main/apps.toml),
[lista de rechazadas](https://github.com/YunoHost/apps/blob/main/rejectedlist.toml),
[Dex en YunoHost](https://apps.yunohost.org/app/dex),
[Pocket ID en YunoHost](https://apps.yunohost.org/app/pocket-id).
Funciones: [Pocket ID y passkeys](https://pocket-id.org/docs/introduction),
[sincronización LDAP Pocket ID](https://pocket-id.org/docs/configuration/ldap),
[MFA Authelia](https://www.authelia.com/overview/authentication/introduction/),
[MFA authentik](https://docs.goauthentik.io/add-secure-apps/flows-stages/stages/authenticator_validate/),
[Keycloak](https://www.keycloak.org/docs/latest/server_admin/).

## Arquitectura para Google, GitHub y Microsoft

```text
                              Google
ASM3 /oidc/login --> Dex -->   GitHub
                              Microsoft
                              LDAP YunoHost

ASM3 /ynh_sso -------------> SSOwat + LDAP YunoHost (acceso nativo conservado)
```

ASM3 mantiene **un emisor OIDC por instancia**. Dex presenta los conectores y
emite el ID token que verifica ASM3; no hace falta implementar tres variantes de
OAuth dentro de ASM3. Usar el emisor Dex mantiene fijo el callback de ASM3 al
incorporar proveedores adicionales.

| Cuenta | Integración directa con ASM3 | Integración común mediante Dex |
| --- | --- | --- |
| Google | OIDC, emisor `https://accounts.google.com`; registrar cliente web y callback ASM3. Usar sujetos autorizados si no recibes grupos. | Conector `google`, cliente web de Google registrado con callback Dex. |
| GitHub | Su OAuth de usuarios no emite ID tokens OIDC. Su discovery de autenticación no lo convierte en IdP de personas. Los tokens OIDC de Actions son para trabajos, no para este login. | OAuth App de GitHub y conector `github`; restringir organización/equipos. |
| Microsoft | OIDC con tenant concreto: `https://login.microsoftonline.com/TENANT_UUID/v2.0`. Registrar cliente web y callback ASM3. No usar `common` como issuer fijo: puede anunciar un issuer con plantilla en lugar del valor exacto del tenant. | Conector `microsoft`, registro Entra y tenant concreto. |

Hay plantillas directas para [Google](examples/asm3-google.json) y
[Microsoft con tenant concreto](examples/asm3-microsoft.json), desactivadas y con
listas vacías para que nadie quede autorizado accidentalmente.
Las opciones directas son plantillas de integración con el cliente genérico; no
se han probado inicios de sesión en cuentas Google/Microsoft reales. La firma
publicada por cada proveedor debe coincidir con el algoritmo seleccionado en ASM3.

Fuentes: [Google OIDC](https://developers.google.com/identity/openid-connect/openid-connect),
[Microsoft OIDC](https://learn.microsoft.com/en-us/entra/identity-platform/v2-protocols-oidc),
[alcance del discovery de GitHub](https://docs.github.com/en/apps/github-authentication-discovery-endpoints),
[conectores Dex](https://dexidp.io/docs/connectors/).

## Configurar Dex en YunoHost

Desde `51.1~ynh6`, el [panel integrado](DEX.md) crea el cliente ASM3 y los tres
conectores sociales, protege los secretos y mantiene callbacks tras cambios de URL.
Usa este panel para la integración gestionada. Los archivos de `examples/` son
referencias para despliegues manuales y no deben duplicar sus conectores.

## Las dos clases de callback

| Registro | Callback de ejemplo |
| --- | --- |
| Cliente ASM3 registrado en Dex | `https://refugio.example.org/asm3/oidc/callback` |
| Aplicación Google/GitHub/Microsoft registrada para Dex | `https://identidad.example.org/dex/callback` |

No intercambies ambos callbacks. El primero termina el acceso en ASM3; el segundo
permite que Dex complete el acceso social. Usa exactamente el issuer Dex real y
su ruta; si está en raíz, omite `/dex`.

Google: crea un cliente web y configura consentimiento/usuarios de prueba según
el estado de la aplicación. El `groups` de OIDC no está disponible para cuentas
Google personales. El conector Dex obtiene grupos Workspace con configuración y
permisos adicionales; no los presupongas. Autoriza sujetos Dex concretos si no hay
grupos, sin abrir la lista a cualquiera con una cuenta Google.

GitHub: registra una OAuth App para Dex, limita organización/equipo y deja
`useLoginAsID: false` para usar el identificador estable de GitHub. Los grupos Dex
se presentan como `organización:equipo`; utiliza los valores realmente emitidos.
La política de 2FA de la organización se configura en GitHub.

Microsoft: registra una aplicación Entra, URI web Dex y secreto. Empieza con
`openid profile email`, tenant concreto y autorización por sujeto. Solo añade
lectura de grupos y consentimiento administrativo si necesitas esos grupos:
no concedas permisos de directorio amplios para un simple login. Las cuentas
personales y empresariales pueden requerir configuraciones distintas.

Conectores: [Google](https://dexidp.io/docs/connectors/google/),
[GitHub](https://dexidp.io/docs/connectors/github/),
[Microsoft](https://dexidp.io/docs/connectors/microsoft/).

## Segundo factor obligatorio en esta integración

Desde `~ynh6`, ASM3 exige inscribir y confirmar TOTP en todas las entradas privadas:
Dex, OIDC directo, SSO/LDAP nativo y recuperación. No depende de las políticas
MFA de los proveedores ni acepta `amr` como excepción. Las API por contraseña se
bloquean. El panel YunoHost permite el alta social y restablecer un factor perdido;
consulta [DEX.md](DEX.md). Los datos y sesiones siguen sometidos a roles, política
OIDC y revocación LDAP en cada petición privada.

## Algoritmos y cuentas vinculadas

Desde `51.1~ynh5`, `id_token_signing_alg` acepta `RS256` o `RS512`. Se fija uno por
cliente y se comprueba en discovery, cabecera JWT, JWK y verificación de firma.
No se rebaja automáticamente a otro algoritmo. PKCE sigue siendo S256 con ambos.
RS512 significa RSA con SHA-512; la clave RSA sigue requiriendo al menos 2048 bits.

**Dex con firmante local solo soporta RS256 según su documentación actual**. Su
firmante Vault tampoco anuncia RS512 en la lista documentada. Mantén RS256 para
Dex; usa RS512 únicamente con un IdP que lo anuncie y lo emita para ese cliente.
Consulta [firmas Dex](https://dexidp.io/docs/configuration/tokens/).

Una persona puede producir distintos `sub` al usar conectores diferentes. ASM3
no fusiona por email. La vinculación LDAP actual admite una identidad OIDC por
perfil; para agrupar varios accesos sociales bajo el mismo perfil conviene que
el IdP los reúna primero en una cuenta y emita un `sub` estable. No cambies
identificadores en producción sin una migración explícita y una copia previa.
