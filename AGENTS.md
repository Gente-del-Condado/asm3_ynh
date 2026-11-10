# Instrucciones para colaborar en ASM3 para YunoHost

Lee [CONTRIBUTING.md](CONTRIBUTING.md) para localizar los componentes y ejecutar las pruebas.
La rama `main` del repositorio es la fuente del paquete. Los artefactos de
`dist/` son generados. No edites una copia extraída como si fuera la fuente.

- Escribe documentación y comentarios nuevos en español. Conserva los
  identificadores, rutas, nombres de herramientas y protocolos originales.
- Limita los comentarios a decisiones, invariantes y efectos secundarios.
- Mantén sincronizados `manifest.toml` y `upstream.lock.json` al cambiar ASM3.
  El código upstream se descarga por commit y SHA-256. Sus cambios locales
  viven en `patches/main/`.
- Conserva el límite de confianza entre SSOwat, Nginx y el backend local. El
  UUID LDAP identifica al usuario. El segundo factor es obligatorio en cada
  acceso privado, incluida la recuperación. Las sesiones y los roles tienen
  pruebas específicas. Evita registrar credenciales o tokens.
- Usa datos ficticios, contenedores desechables y un entorno aislado para
  pruebas de integración. No agregues bases, claves, sesiones, registros
  privados ni resultados sin revisar a Git.
- Antes de entregar, ejecuta el verificador del paquete y las pruebas
  unitarias. Para cambios en instalación, persistencia, permisos o proxy,
  sigue la matriz de [pruebas](doc/TESTING.md) y registra el commit probado.
- Edita el manual en `docs/` y los textos consumidos por YunoHost en `doc/`.
  Actualiza ambos si cambia un paso que describen. Las variables como
  `__APP__` en los textos de YunoHost se sustituyen al mostrarlos.
