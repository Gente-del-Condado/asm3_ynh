# Fuentes del manual

La página se publica desde `docs/` como HTML y CSS estáticos. Edita los textos en
`index.html`, los estilos en `assets/manual.css` y el ejemplo de Home Assistant
en `assets/home-assistant.yaml`. Las rutas de recursos son relativas para que
funcionen desde la raíz del sitio o bajo la subruta del repositorio.

Las capturas WebP se hicieron en una instancia de laboratorio de ASM3 con datos
ficticios. La pantalla de MFA muestra la verificación con el campo vacío.
Conserva textos alternativos descriptivos y ajusta los atributos `width` y
`height` si sustituyes imágenes. Nunca captures códigos activos, claves de alta,
datos personales ni registros de producción.

Consulta [CONTRIBUTING.md](../CONTRIBUTING.md) para previsualizar el manual y
[la guía de publicación](../doc/PUBLISHING.md#publicar-el-manual-con-github-pages)
para activar GitHub Pages. `.nojekyll` indica que los archivos se sirven tal cual.
