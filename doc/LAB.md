# Laboratorio de pruebas de esta entrega

Se ha preparado un laboratorio aislado para ejecutar `package_check`, sin instalar
Incus ni YunoHost en el sistema Fedora del usuario:

- QEMU 10.2.2 con KVM, 4 vCPU y 4 GiB de RAM.
- Máquina virtual Debian 13, con Incus 6.0.4.
- Red privada `incusbr0` y almacenamiento Btrfs sobre un disco virtio dedicado.
- Imagen oficial `yunohost/bookworm-stable/appci/amd64`, serie `202609042148`.
- Huella de la imagen:
  `91abc4fc4c435cd619e85fb5f9fc173393ceae8b795819107eaf9fceb0985ab7`.
- Sistema probado: Debian 12, YunoHost 12.1.41.2, arquitectura amd64.
- Herramienta oficial `YunoHost/package_check`, commit
  `f7d32cadac3cfced282decede024707fba9e6ec6`.

Los discos y las claves del laboratorio quedan en `.test-env/`, excluido del Git y
de los archivos de distribución. SSH se limita al puerto 22227 de 127.0.0.1. No se
publican servicios ni se cambian las instalaciones Podman existentes del host.

La configuración inicial de snapshots sobre un archivo loopback provocó una
ralentización de E/S; se sustituyó por el disco dedicado antes de realizar la matriz
válida. La VM utiliza caché de escritura para pruebas desechables. No es una
recomendación de almacenamiento para producción.

Para repetir en un host de laboratorio Debian con Incus configurado, instala las
dependencias indicadas por el proyecto oficial `package_check`, incluyendo
`dnsmasq-base`, `lynx`, `jq`, `git`, `btrfs-progs` y las dependencias Python de su
`requirements.txt`. Usa un venv si la distribución protege el Python del sistema.
Después ejecuta desde este repositorio:

```bash
bash tools/run_package_check.sh
```

El ejecutor crea una copia Git limpia del contenido distribuible, importa la imagen
oficial con el alias local que espera el checker si es necesario, lanza la matriz y
conserva sus resultados en `.package-check/results/`. No modifica las pruebas del
proyecto oficial ni simula el gestor de paquetes de YunoHost.

La repetición final reutiliza una imagen derivada del snapshot de dependencias que
el propio checker creó antes de instalar ASM3, con huella
`950ecf6981aebbb1c84a9d375d2f5b7d998eb4316e3e7412b330f82502cebdce`.
Así se evitan nuevas instalaciones de los mismos paquetes apt; las pruebas y el
ciclo de vida de ASM3 se vuelven a ejecutar completos sobre el artefacto final.
