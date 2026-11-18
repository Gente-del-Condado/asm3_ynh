# Publicar en GitHub y Forgejo

## Recorrido con espejo privado

La ruta es Forgejo → `asm3_ynh-private` (Actions desactivado) → `asm3_ynh`
público → instalación personalizada de YunoHost. La raíz pública ya es el paquete;
no hace falta otro repositorio por tienda. La aceptación en el catálogo oficial
es independiente de esta automatización.

Forgejo escribe en el privado con una clave SSH exclusiva. El público lee ese
espejo mediante `MIRROR_READ_TOKEN`, limitado a Contents/Metadata de lectura del
único privado. El diagnóstico manual exige el SHA completo de Forgejo y comprueba
identidad, privacidad, rutas y origen upstream fijado sin ejecutar las fuentes.

`publish-mirror.yml` comprueba cada hora el main privado. Exporta únicamente las
rutas revisadas de `.github/asm-publication/public-files.txt`, valida el paquete,
las pruebas unitarias, MariaDB y su empaquetado en un job sin credenciales de
publicación. Otro job verifica SHA, hashes y permisos, y escribe solo en el público
con su propio `GITHUB_TOKEN`. Después publica Pages. No importa workflows del
privado automáticamente, no reescribe el historial ni copia ramas privadas.
Esta primera versión publica main; no crea ni mueve etiquetas.

La activación requiere `ENABLE_MIRROR_PUBLICATION=true` en el público y, en una
ejecución manual, seleccionar publicar. Sin esa variable solo se valida. Antes
de activarla se aísla el espejo directo público antiguo: intervalo `0s`, filtro
`migration-disabled/no-direct-publication`. No crear esa rama reservada. Su clave
se conserva temporalmente para reversión; no es necesaria en la ruta nueva.
El espejo privado conserva sincronización al recibir commits e intervalo 10m.

Los cambios del controlador y la lista pública se revisan primero en Forgejo y
se trasladan expresamente al público. Los cambios del producto siguen la ruta
anterior. Si aparece un archivo nuevo bajo los directorios del paquete, la
publicación se detiene hasta revisar la lista permitida.

## Subir el repositorio

Publica desde el checkout Git para conservar su historial. Configura solo los
remotos que vayas a usar y sustituye las URLs de ejemplo:

```bash
git remote add origin ssh://forgejo@TU_FORGEJO/TU_USUARIO/asm3_ynh.git
git push origin HEAD:refs/for/main/mantenimiento
```

Revisa y fusiona la propuesta en Forgejo; su espejo lleva main al privado de GitHub.
Los bundles de `dist/` sirven para instalar o transportar el paquete. Mantén
discos de laboratorio, credenciales y copias de producción fuera del checkout.

Una vez publicado, YunoHost acepta la URL del repositorio de cualquiera de las dos
forjas como aplicación personalizada. La raíz debe contener `manifest.toml` y
`scripts/`. No subas únicamente el tar comprimido como contenido del repositorio.

## GitHub

Solo en `asm3_ynh` público, activa Actions. Permite que los workflows creen PRs en Settings → Actions → General.
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

## Forgejo y comprobación del recorrido

Mantén el espejo privado activo y Actions desactivado en Forgejo y GitHub privado.
Compara main de Forgejo con main del privado. El público lleva commits propios:
consulta `.publication/asm3.json` para su `source_sha` y hashes de archivos.
No compares directamente el SHA del commit público con el privado tras activar
la exportación. Sin cambios de origen el workflow termina sin repetir pruebas
costosas ni publicar de nuevo. La matriz del laboratorio sigue siendo manual.

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
