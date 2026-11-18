# Publicar en GitHub y Forgejo

Forgejo conserva el origen y replica hacia GitHub. Solo `.github/workflows/`
ejecuta la validación, el seguimiento upstream, la matriz YunoHost manual y Pages.
Actions permanece desactivado en Forgejo; sus antiguos workflows específicos se
han retirado para evitar dos recorridos de CI. Los cambios se preparan en Forgejo.

## Subir el repositorio

Publica desde el checkout Git para conservar su historial. Configura solo los
remotos que vayas a usar y sustituye las URLs de ejemplo:

```bash
git remote add origin ssh://forgejo@TU_FORGEJO/TU_USUARIO/asm3_ynh.git
git push origin HEAD:refs/for/main/mantenimiento
```

Revisa y fusiona la propuesta en Forgejo; su espejo lleva main a GitHub.
Los bundles de `dist/` sirven para instalar o transportar el paquete. Mantén
discos de laboratorio, credenciales y copias de producción fuera del checkout.

Una vez publicado, YunoHost acepta la URL del repositorio de cualquiera de las dos
forjas como aplicación personalizada. La raíz debe contener `manifest.toml` y
`scripts/`. No subas únicamente el tar comprimido como contenido del repositorio.

## GitHub

Activa Actions. Permite que los workflows creen PRs en Settings → Actions → General.
La validación funciona en un runner Ubuntu alojado. El seguimiento de versiones usa
`GITHUB_TOKEN` del propio repositorio. Las propuestas upstream se revisan y se trasladan al origen Forgejo antes de
fusionar allí; no se fusionan automáticamente sobre el espejo GitHub.

### Publicar el manual con GitHub Pages

El manual es un sitio estático en `docs/`. Incluye `index.html`, los recursos
con rutas relativas y `.nojekyll`, así que funciona también bajo una subruta.
En GitHub, selecciona **Settings → Pages → Source → GitHub Actions**.
El workflow `.github/workflows/pages.yml` publica `docs/` cuando cambia el
manual en `main`. También se puede ejecutar manualmente desde Actions.

El manual solo contiene ejemplos y capturas de laboratorio. No copies datos
privados a `docs/`, que se sirve como sitio público en la configuración habitual.
Consulta la [guía oficial de GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

## Forgejo

Mantén activo el espejo de salida hacia GitHub y desactiva Actions en Forgejo. No se necesita un token de CI
Forgejo ni un runner en YunoHost para los flujos de este paquete. Se conservan las
herramientas de laboratorio y `tools/run_package_check.sh` para pruebas explícitas.

## Sincronizar main y actualizar Pages

Forgejo es el origen de `main`. El espejo de salida del repositorio envía
esa rama a GitHub mediante SSH cuando recibe cambios y vuelve a comprobarla
cada diez minutos. GitHub autoriza la clave pública del espejo como clave de
despliegue con escritura solo en `Gente-del-Condado/asm3_ynh`.

Sube los cambios a Forgejo. El espejo puede sobrescribir cambios divergentes
en `main` de GitHub. Para diagnosticar una actualización, revisa el espejo en
los ajustes del repositorio de Forgejo y el workflow de Pages en GitHub.

Para comprobar la sincronización, compara el identificador del commit de `main`
en ambas forjas. Cada push replicado activa `Validate package` en GitHub. Pages
solo se publica cuando cambia `docs/` o su propio workflow; un cambio únicamente
en `doc/` no necesita volver a publicar el manual.

## Matriz integral de YunoHost en CI

El workflow `.github/workflows/package-check.yml` es manual. Usa un runner de laboratorio con
Incus/LXD configurado y las dependencias oficiales de `package_check`. En GitHub
necesita las etiquetas `self-hosted`, `linux`, `yunohost-package-check`; el runner debe estar preparado explícitamente para ese laboratorio.

Este llama a `tools/run_package_check.sh`. Guarda consola, log completo, JSON y
commit de la herramienta en `.package-check/results/`. El wrapper devuelve error
si falla una prueba, incluso cuando el lanzador oficial termina con código 0.
El chequeo de pertenencia al catálogo seguirá fallando hasta que la comunidad
acepte el paquete en su catálogo; no se falsea ese resultado.
Aunque las siete pruebas funcionales tengan `main_result=success`, el workflow
integral también devuelve error si el nivel oficial sigue en 0 por los hallazgos
del linter. La validación ordinaria del paquete y sus pruebas MariaDB son jobs
independientes de esa aceptación administrativa.
