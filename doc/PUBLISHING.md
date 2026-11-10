# Publicar en GitHub y Forgejo

El mismo repositorio funciona en ambas forjas. Contiene workflows independientes:

| Directorio | Uso |
| --- | --- |
| `.github/workflows` | GitHub Actions: validación, actualización estable y matriz YunoHost manual |
| `.forgejo/workflows` | Forgejo Actions: los mismos procesos con acciones compatibles y API propia |

## Subir el repositorio

Publica desde el checkout Git para conservar su historial. Configura solo los
remotos que vayas a usar y sustituye las URLs de ejemplo:

```bash
git remote add github https://github.com/TU_USUARIO/asm3_ynh.git
git remote add forgejo https://TU_FORGEJO/TU_USUARIO/asm3_ynh.git
git push -u github main
git push forgejo main
```

Si Forgejo ya está configurado como `origin`, usa `git push origin main`.
Los bundles de `dist/` sirven para instalar o transportar el paquete. Mantén
discos de laboratorio, credenciales y copias de producción fuera del checkout.

Una vez publicado, YunoHost acepta la URL del repositorio de cualquiera de las dos
forjas como aplicación personalizada. La raíz debe contener `manifest.toml` y
`scripts/`. No subas únicamente el tar comprimido como contenido del repositorio.

## GitHub

Activa Actions. Permite que los workflows creen PRs en Settings → Actions → General.
La validación funciona en un runner Ubuntu alojado. El seguimiento de versiones usa
`GITHUB_TOKEN` del propio repositorio. `ASM3_AUTO_MERGE=true` es opcional y requiere
configurar auto-merge y las protecciones de rama correspondientes.

### Publicar el manual con GitHub Pages

El manual es un sitio estático en `docs/`. Incluye `index.html`, los recursos
con rutas relativas y `.nojekyll`, así que funciona también bajo una subruta.
Tras replicar el repositorio en GitHub, abre **Settings → Pages**, selecciona
**Deploy from a branch**, elige **main /docs** y guarda. La URL la muestra
GitHub cuando el despliegue termina. Revisa que la página y las imágenes se
carguen bajo la URL publicada.

El manual solo contiene ejemplos y capturas de laboratorio. No copies datos
privados a `docs/`, que se sirve como sitio público en la configuración habitual.
Consulta la [guía oficial de GitHub Pages](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).

## Forgejo

Activa Actions para el repositorio y conecta un runner cuya etiqueta `docker` use
contenedores. Los jobs usan `data.forgejo.org/oci/node:22-bookworm`; instalan las
dependencias dentro del job y no requieren que el servidor Forgejo sea Debian.

La validación de pushes/PRs no necesita un token personal. Para que el seguimiento
diario pueda subir su rama y crear una propuesta, añade el secreto Actions
**`ASM3_UPDATE_TOKEN`**, limitado a este repositorio, con permiso de escritura del
repositorio y sus pull requests. Nunca lo añadas a archivos Git. El script usa
`FORGEJO_SERVER_URL` y `FORGEJO_REPOSITORY` que proporciona el runner; no depende de
GitHub CLI ni de un dominio Forgejo fijo. No activa fusión automática en Forgejo.

Si mantienes un espejo en ambas forjas, activa el seguimiento diario en una sola
para evitar propuestas duplicadas. Replicar Git no replica secretos, runners ni
configuración de Actions.

## Matriz integral de YunoHost en CI

Los workflows `package-check.yml` son manuales. Usa un runner de laboratorio con
Incus/LXD configurado y las dependencias oficiales de `package_check`. En GitHub
necesita las etiquetas `self-hosted`, `linux`, `yunohost-package-check`; en Forgejo,
la etiqueta `yunohost-package-check` debe ejecutar directamente en ese host.

Ambos llaman a `tools/run_package_check.sh`. Guarda consola, log completo, JSON y
commit de la herramienta en `.package-check/results/`. El wrapper devuelve error
si falla una prueba, incluso cuando el lanzador oficial termina con código 0.
El chequeo de pertenencia al catálogo seguirá fallando hasta que la comunidad
acepte el paquete en su catálogo; no se falsea ese resultado.
Aunque las siete pruebas funcionales tengan `main_result=success`, el workflow
integral también devuelve error si el nivel oficial sigue en 0 por los hallazgos
del linter. La validación ordinaria del paquete y sus pruebas MariaDB son jobs
independientes de esa aceptación administrativa.

Las acciones Forgejo se eligieron según la
[referencia oficial](https://forgejo.org/docs/latest/user/actions/reference/) y la
[guía de uso](https://forgejo.org/docs/latest/user/actions/actions/).
