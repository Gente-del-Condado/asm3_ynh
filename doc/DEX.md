# Dex, proveedores sociales y segundo factor obligatorio

Versión `51.1~ynh6`. La aplicación conserva el SSO nativo y la autorización LDAP.
Dex es una aplicación compartida independiente; el paquete no instala otro proxy
ni modifica el SSO global de YunoHost. Se ha probado con Dex `2.46.1~ynh1`.

## Configuración desde YunoHost

1. Instala **Dex** desde el catálogo de YunoHost, en HTTPS con certificado válido.
2. Abre **Aplicaciones → Animal Shelter Manager → Configuración → Identidad y segundo factor**.
3. Activa Dex y selecciona su identificador (`dex`). Conserva LDAP si deseas
   ofrecerlo también dentro de Dex. El SSO nativo `/ynh_sso` permanece disponible.
4. Registra los clientes que quieras usar en las consolas de los proveedores.
   El panel muestra dos callbacks: ASM3 `/oidc/callback` se registra automáticamente
   en Dex; los tres proveedores externos deben usar el callback **de Dex** `/callback`.
5. Activa Google, GitHub o Microsoft, introduce Client ID y Client Secret y guarda.
   Microsoft requiere el UUID de un tenant concreto; esta interfaz no admite
   `common` ni cuentas personales. Los tres proveedores son independientes.
6. Autoriza correos **verificados y completos**, grupos o sujetos Dex. Cualquiera
   de las tres listas puede autorizar un perfil; vacías deniegan todos los accesos
   externos. No son comodines ni una asignación de privilegios. Para LDAP puedes
   usar un grupo real autorizado de YunoHost, por ejemplo un grupo dedicado al refugio.
7. Entra en ASM3. Un visitante se dirige a Dex; también existe `/oidc/login`.
   Inscribe el TOTP mostrado y confirma su primer código. Los perfiles externos
   son de solo lectura; un administrador ASM3 asigna sus otros roles.

Los campos de contraseña aparecen vacíos al volver al panel. Dejarlos vacíos
conserva el secreto anterior; introducir otro lo rota. Desactivar un proveedor lo
retira de Dex pero conserva sus credenciales en el estado root para reactivarlo.
Para borrarlas definitivamente, desactívalo y elimina esos valores del archivo
`identity_admin.json` como root. Los secretos también forman parte del backup:
protege y cifra tus copias.

El campo de CA es opcional para un certificado público válido. En un laboratorio
con CA privada proporciona un archivo PEM absoluto de confianza; se copia a un
archivo protegido legible por el servicio. No se desactiva la validación TLS.

## Registro de cada proveedor

- **Google:** cliente OAuth para aplicación web y pantalla de consentimiento;
  URI autorizada exacta `https://TU_DEX/RUTA/callback`. Para cuentas personales
  usa direcciones verificadas concretas o sujetos. Los grupos Workspace requieren
  una cuenta de servicio y permisos adicionales, fuera del panel básico.
  [Conector oficial](https://dexidp.io/docs/connectors/google/).
- **GitHub:** registra una OAuth App con ese callback Dex. Opcionalmente limita
  organización y equipo en el panel; la organización puede exigir aprobar el
  acceso de la aplicación. Se usa el ID estable, no el login mutable. Los grupos
  que emite Dex tienen formato `organizacion:equipo`.
  [Conector oficial](https://dexidp.io/docs/connectors/github/).
- **Microsoft Entra:** registra una aplicación de un tenant concreto, añade una
  URI Web para el callback Dex y un secreto de cliente. Copia Application/Client
  ID y Directory/Tenant ID. Los grupos requieren consentimiento del administrador
  para los permisos de lectura de directorio del conector (`Directory.Read.All`). El
  conector conserva `User.Read` para obtener el perfil con Microsoft Graph. Si no
  tienes consentimiento para grupos, deja vacía la lista de grupos y usa
  sujetos o correos que Dex marque expresamente como verificados; un correo no
  verificado nunca autoriza. [Conector oficial](https://dexidp.io/docs/connectors/microsoft/).

No se crean registros ni secretos en cuentas cloud automáticamente. Las pruebas
inicializan los conectores reales con credenciales de fixture y prueban un flujo
completo Dex/LDAP; no representan un login a cuentas cloud reales.

## MFA en todas las vías de acceso privado

Se exige un código TOTP de seis dígitos cada 30 segundos después del primer factor,
incluidos portal YunoHost, Dex LDAP, Google/GitHub/Microsoft, OIDC directo y cuenta
local de recuperación. La política no depende de Force2FA ni de `acr`/`amr` del IdP.
Si ya existe un factor en ASM3 se reutiliza. Antes de confirmarlo no hay sesión
privada con usuario, roles o conexión, y las acciones privadas quedan bloqueadas.

La pantalla ofrece QR y clave manual, no incluye secretos en URL y exige CSRF en
los POST. La comprobación pendiente caduca en cinco minutos; un código aceptado
no puede reutilizarse, ni en otro navegador. Cinco fallos bloquean durante cinco
minutos. La prueba MFA dura como máximo ocho horas y nunca supera la sesión OIDC.
La cuenta deshabilitada, la revocación LDAP o un cambio de política siguen
invalidando el acceso. No hay remember-me. El restablecimiento de contraseña
conserva el factor. Las API autenticadas por contraseña se bloquean por completo;
los formularios/adopciones y servicios públicos mantienen su acceso configurado.

**Recuperación de un factor perdido:** abre la sección Recuperación del mismo panel,
introduce el nombre exacto de usuario ASM3 y pulsa Restablecer MFA. Es una acción
de administrador YunoHost/root. Invalida sesiones y comprobaciones pendientes;
el próximo acceso requiere primer factor y nueva inscripción. La cuenta local de
recuperación también exige TOTP. No existe código maestro ni bypass.

La base de datos contiene semillas TOTP como requiere ASM3: respalda y protege la
base de datos y sus copias. Una cuenta social comprometida que nunca inscribió MFA
podría completar su primer alta; el alta inicial presupone controlar el primer
factor legítimo. Distribuye el acceso inicial y los restablecimientos con cuidado.

## Ciclo de vida y coexistencia

El panel genera conectores `asm3-<instancia>-<proveedor>`, un cliente independiente,
un EnvironmentFile root 0600 y un drop-in systemd de Dex. No sobrescribe clientes
ni conectores ajenos. El JSON de credenciales del panel es root 0600; ASM3 solo
lee su configuración OIDC root:app 0640. El getter y los mensajes de fallo no
muestran los secretos. Los diffs de helpers se filtran antes de entrar en consola
o registros. Aplicar valida discovery y espera hasta 60 segundos a la inicialización
de Dex antes de revertir archivos si falla. El cliente
usa `client_secret_post` por HTTPS para evitar que SSOwat interprete Basic como
credenciales del portal. La opción de entrada externa solo retira visitantes
que esta integración añadió; conserva los permisos públicos preexistentes.

Al cambiar la URL de ASM3 se actualiza su callback en Dex. Los hooks de instalación,
actualización, restauración y cambio de URL de Dex reconcilian esta integración.
Si cambia la URL **de Dex**, cambia también el callback en las tres consolas cloud.
Desactivar la integración restaura el OIDC anterior; desinstalar ASM3 retira solo
sus conectores/cliente, manteniendo Dex y otras aplicaciones. No se borran datos
OAuth ajenos en el almacenamiento de Dex. Los conectores se añaden al selector
compartido de Dex; cada aplicación debe conservar su propia política de acceso.

La copia ASM3 incluye configuración, secretos protegidos y estado MFA SQL. Restaura
Dex antes de ASM3 si necesitas login externo inmediatamente; si falta Dex, se
conservan las vías nativa y local, ambas con MFA. Los hooks reactivan la integración
al restaurar/instalar Dex. La configuración root tiene autoridad sobre los roles:
no se vinculan cuentas LDAP automáticamente por coincidencia de correo.

Dex firma localmente con RS256. El OIDC genérico conserva la selección RS256/RS512
mediante `manage_oidc.py`; no se fuerza RS512 a un Dex que no lo anuncia.
El modo gestionado y el genérico comparten un solo emisor por instancia; desactiva
la gestión Dex antes de configurar otro IdP manualmente.
