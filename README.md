# Animal Shelter Manager para YunoHost

![Animal Shelter Manager](https://raw.githubusercontent.com/Gente-del-Condado/asm3_ynh/main/doc/logo.png)

Paquete nativo de **ASM3** para **YunoHost ≥ 12.1.17**, formato de empaquetado 2 y
helpers 2.1. La versión empaquetada es **51-1** (`51.1~ynh9`), con origen fijado al **5 de noviembre de 2026**. El código se descarga del repositorio
oficial, fijado por commit y SHA-256; no depende de una imagen Docker.

Preparado para publicarse en **GitHub o Forgejo**, con workflows propios para
ambas plataformas. Consulta [la guía de publicación](doc/PUBLISHING.md).

## Documentación

- [Manual web en español](https://gente-del-condado.github.io/asm3_ynh/). Consulta cómo [publicarlo con GitHub Pages](doc/PUBLISHING.md#publicar-el-manual-con-github-pages).
- [Administración en YunoHost](doc/ADMIN_es.md), [SSO y LDAP](doc/SSO.md), [Dex](doc/DEX.md) y [OIDC](doc/OIDC.md).
- [Monitorización con Home Assistant](doc/HOME_ASSISTANT.md).
- [Desarrollo](CONTRIBUTING.md) e [instrucciones para agentes](AGENTS.md).

## Instalación

Con este directorio copiado al servidor YunoHost:

```bash
sudo yunohost app install /ruta/absoluta/asm3_ynh
```

Si usas el archivo de entrega, descomprímelo antes:

```bash
mkdir asm3_ynh
tar -xzf 'asm3_ynh-51.1~ynh9.tar.gz' -C asm3_ynh
sudo yunohost app install "$PWD/asm3_ynh"
```

El asistente solicita dominio, ruta, grupo con acceso, administrador e idioma.
Puedes instalar en `/` o en `/asm3`, usar español y desplegar varias instancias.
Entra desde el portal de YunoHost: el usuario elegido será administrador de ASM3.
El esquema, las plantillas, los informes y los formularios se preparan automáticamente.

Puedes instalar desde la URL del repositorio en “Instalar una aplicación
personalizada” de YunoHost si el servidor puede clonarlo. Si el repositorio
requiere autenticación, clónalo en el servidor y usa la ruta local.

## Qué incluye

- Aplicación oficial con Nginx, Cheroot/WSGI en loopback, systemd y MariaDB.
- Dependencias para PDF, etiquetas, Excel, QR, imágenes, vídeo, S3 e integraciones.
- Administrador creado al instalar y cuentas predeterminadas deshabilitadas.
- Cookies por instancia y ruta; HTTPS y puerto interno sin exponer al exterior.
- Tareas diarias, publicación y envío horario de informes, con bloqueo durante
  mantenimiento para evitar interferencias con las copias y migraciones.
- Scripts de instalación, actualización, eliminación, copia/restauración y cambio
  de URL; documentos y fotografías incluidos en la copia SQL.
- Actualizador de versiones, CI, pruebas reales con MariaDB y archivo distribuible.

El acceso usa **SSO nativo de YunoHost y perfiles automáticos desde LDAP**. El
permiso `asm3.staff` autoriza al personal; inicialmente incluye `all_users`.
Los nuevos perfiles reciben solo lectura de animales; asigna otros roles en ASM3.
El administrador elegido conserva el acceso completo. No se copia ni almacena la
contraseña de YunoHost en ASM3. La vinculación usa `entryUUID`, evitando apropiarse
de cuentas anteriores al recrear un usuario con el mismo nombre.

Para formularios/adopciones/API públicos, configura ASM3 y permite visitantes en
`asm3.main`. Mantén `asm3.staff` limitado al personal: abrir el permiso principal
no otorga permisos internos. Desde esta versión se bloquean las API autenticadas por contraseña, para impedir
un acceso sin segundo factor. Los servicios públicos de ASM3 siguen disponibles.

La recuperación local está en `/login?local=1`. Como root puedes consultar su
usuario `ynh_rescue_asm3` y contraseña con `yunohost app setting asm3 rescue_password`.
Consulta [la integración SSO y su administración](doc/SSO.md), incluyendo 2FA,
revocación, cierre de sesión y migración desde `~ynh2`.

## Dex, Google, GitHub, Microsoft y 2FA obligatorio

Instala **Dex** desde el catálogo y abre **Aplicaciones → Animal Shelter Manager →
Configuración → Identidad y segundo factor**. Activa los proveedores deseados y
pega sus identificadores/secrets registrados. El panel muestra el callback correcto,
crea el cliente ASM3 en Dex y conserva los conectores de otras aplicaciones.
Autoriza correos verificados concretos, grupos o sujetos: las listas vacías deniegan
el acceso. El inicio externo queda en `/oidc/login`; `/ynh_sso` conserva el acceso nativo.

**Todos los accesos privados exigen TOTP**, incluido SSO nativo/LDAP, cuentas OIDC
y recuperación local. El primer acceso obliga a inscribir y confirmar un factor;
no entrega datos ni ejecuta acciones privadas antes de verificarlo. El panel
permite al administrador root restablecer un factor perdido. No hay excepción
por `amr` del proveedor, remember-me ni API por contraseña.

Consulta [la guía de configuración Dex y MFA](doc/DEX.md). Debes registrar los
clientes en las consolas de Google/GitHub/Microsoft y aportar sus credenciales;
el paquete no crea aplicaciones en tus cuentas externas.

## OpenID Connect opcional

También puedes usar un proveedor OpenID Connect conservando SSO nativo y LDAP.
Incluye Authorization Code con PKCE S256, firma RS256/RS512 seleccionable, perfiles de solo lectura,
listas explícitas de sujetos/grupos y vinculación LDAP controlada por root.
El acceso OIDC es `/oidc/login`; el acceso nativo sigue siendo `/ynh_sso`.

OIDC se entrega desactivado hasta registrar tu cliente y configurar su emisor y
credenciales. El configurador valida discovery y aplica el archivo sin imprimir
secretos. Consulta [la guía OIDC](doc/OIDC.md), con URI exactas, configuración,
logout, copias y límites de revocación.

Consulta también [proveedores con MFA e integración Google/GitHub/Microsoft](doc/IDENTITY_PROVIDERS.md).

## Actualizaciones automáticas del paquete

Al publicar el repositorio en GitHub, activa Actions y permite que sus workflows
creen pull requests en Settings → Actions → General. El workflow
`update-upstream.yml` comprueba diariamente la última **release estable** oficial:

1. Resuelve la etiqueta, incluso si es anotada, hasta su commit exacto.
2. Descarga el archivo de ese commit y calcula SHA-256.
3. Actualiza `manifest.toml`, `upstream.lock.json` y la versión del paquete.
4. Ejecuta las validaciones y el ciclo real de MariaDB; genera un archivo instalable.
5. Abre o actualiza una PR en `automation/asm3-stable`.

Por defecto se revisa y fusiona la PR. Para fusionar automáticamente, habilita
auto-merge en el repositorio y crea la variable Actions **`ASM3_AUTO_MERGE=true`**.
Configura las protecciones de rama que desees antes de activarlo. Los workflows
ejecutados con `GITHUB_TOKEN` no desencadenan nuevos workflows al crear la PR; por
eso el actualizador ejecuta sus propias pruebas antes de publicarla. Si impones un
check de PR adicional obligatorio, necesitarás adaptar el token/permisos para que
ese check se dispare. Las tareas programadas de GitHub requieren un repositorio
activo y Actions habilitado; su ejecución puede retrasarse.

También puedes actualizar el paquete manualmente con Python ≥ 3.11:

```bash
python3 tools/update_upstream.py --check  # 0: actual; 1: hay una actualización
python3 tools/update_upstream.py          # actualiza manifest y lock
```

El seguimiento automático prepara nuevas versiones del **repositorio**. Las
instalaciones se actualizan desde YunoHost, conservando su copia de seguridad:

```bash
sudo yunohost app upgrade asm3 -u /ruta/absoluta/asm3_ynh
# O usa la URL real de tu repositorio publicado como argumento de -u.
```

No se descarga `master` durante cada instalación: actualmente marca **52u**, una
versión en desarrollo. Cuando se publique una nueva estable, el workflow la
detectará. Si upstream mueve una etiqueta existente, el commit/checksum cambia y
el actualizador incrementa la revisión `~ynh`.

## Copias de seguridad y administración

```bash
sudo yunohost backup create --apps asm3
sudo yunohost backup list
sudo yunohost backup restore NOMBRE_DE_COPIA --apps asm3
sudo journalctl -u asm3 -n 100 --no-pager
```

La restauración normal se realiza con la aplicación ausente. Los datos, imágenes y
documentos están en MariaDB y entran también en la copia previa a actualizar.
`data_dir` contiene solo caché y un bloqueo. Mantén `dbfs_store = database` para
conservar esta garantía. Configura organización, zona horaria y correo desde ASM3;
las credenciales SMTP locales las aporta el recurso de correo de YunoHost.

Consulta [la guía de administración](doc/ADMIN.md),
[el análisis de integración](doc/INTEGRATION.md) y
[la validación y pruebas](doc/TESTING.md).

## Construcción y publicación

```bash
python3 tools/check_package.py
python3 -m unittest discover -s tests -v
bash tools/build_release.sh
```

El archivo generado en `dist/` contiene la estructura del repositorio; el código de
ASM3 se descarga al instalar y se comprueba contra el SHA-256 del manifest. No es un
instalador sin conexión. También se genera un repositorio Git autocontenido:

```bash
git clone 'dist/asm3_ynh-51.1~ynh9.bundle' asm3_ynh
```

Publica el checkout Git completo para incluir los workflows de CI, el manual y
el seguimiento de versiones. La licencia del paquete y de ASM3 es GPL-3.0-only.

La matriz completa de `package_check` para `51.1~ynh8` obtuvo 7 resultados
`success` en Debian 12 y YunoHost 12.1.41.2. El nivel oficial sigue en 0 por los
hallazgos del catálogo comunitario. Consulta el [JSON original del commit probado](doc/validation/package-check-51.1~ynh8.json)
y la [guía de pruebas](doc/TESTING.md).
