# Publicar en GitHub y Forgejo

El mismo repositorio funciona en ambas forjas. Contiene workflows independientes:

| Directorio | Uso |
| --- | --- |
| `.github/workflows` | GitHub Actions: validación, actualización estable y matriz YunoHost manual |
| `.forgejo/workflows` | Forgejo Actions: los mismos procesos con acciones compatibles y API propia |

## Subir el repositorio

Puedes partir del archivo Git autocontenido generado en `dist/`:

```bash
git clone 'asm3_ynh-51.1~ynh3.bundle' asm3_ynh
cd asm3_ynh
git remote remove origin
git remote add github https://github.com/TU_USUARIO/asm3_ynh.git
git remote add forgejo https://TU_FORGEJO/TU_USUARIO/asm3_ynh.git
git push -u github main
git push forgejo main
```

Crea primero los repositorios vacíos en tus cuentas; no añadas README ni licencia
desde sus interfaces. Los destinos anteriores son ejemplos: sustitúyelos por tus
URLs reales. No se han creado repositorios remotos ni configurado tokens en esta
entrega. No publiques `.test-env/`: contiene discos y claves privadas del laboratorio
local y ya está excluido de Git y de los archivos de distribución.

Una vez publicado, YunoHost acepta la URL del repositorio de cualquiera de las dos
forjas como aplicación personalizada. La raíz debe contener `manifest.toml` y
`scripts/`. No subas únicamente el tar comprimido como contenido del repositorio.

## GitHub

Activa Actions. Permite que los workflows creen PRs en Settings → Actions → General.
La validación funciona en un runner Ubuntu alojado. El seguimiento de versiones usa
`GITHUB_TOKEN` del propio repositorio. `ASM3_AUTO_MERGE=true` es opcional y requiere
configurar auto-merge y las protecciones de rama correspondientes.

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
