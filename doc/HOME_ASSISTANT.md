# Monitorizar ASM3 desde Home Assistant

ASM3 se instala en YunoHost. En Home Assistant puedes añadir una entidad para
comprobar que el servicio responde. Este ejemplo usa la integración REST
incorporada, sin instalar una integración personalizada ni un complemento.

## Si ASM3 ya admite visitantes

1. Prueba la URL de salud desde la red de Home Assistant. Sustituye el dominio y
   la ruta. Si instalaste ASM3 en raíz, elimina `/asm3`.

   ```bash
   curl --fail --silent --show-error https://refugio.example.org/asm3/_ynh_health
   ```

   La respuesta esperada es `ready`. Si aparece una redirección al portal,
   conserva los permisos actuales y usa la opción para instancias privadas.

2. Copia el [ejemplo YAML](../docs/assets/home-assistant.yaml) a
   `configuration.yaml` y ajusta `resource`. Si ya tienes `binary_sensor:`,
   añade solo el elemento `- platform: rest` a su lista.
3. Valida la configuración y reinicia Home Assistant. Busca la entidad «ASM3
   responde» y comprueba el ID asignado en **Ajustes → Dispositivos y servicios
   → Entidades**.
4. En el editor de automatizaciones puedes avisar al equipo cuando la entidad
   pase a `off` o `unavailable` durante cinco minutos. Añade una acción con tu
   canal de notificaciones y usa una duración superior al intervalo de sondeo.

El sensor usa HTTPS con verificación de certificado. Comprueba que la petición
alcanza el backend a través de YunoHost. `ready` no verifica MariaDB, LDAP, Dex,
las adopciones ni las copias. La configuración no incluye contraseñas ni usa
las API de contraseña que desactiva el paquete para proteger MFA.

## Si ASM3 es privado

Mantén restringido el permiso `main`. La integración Ping (ICMP) de Home
Assistant puede comprobar que el servidor responde en la red. Se configura en
**Ajustes → Dispositivos y servicios → Añadir integración → Ping (ICMP)**.
El resultado mide conectividad, no disponibilidad de ASM3. Para comprobar
ASM3 desde el servidor, consulta [la guía de administración](ADMIN_es.md).

- [Sensor binario REST de Home Assistant](https://www.home-assistant.io/integrations/binary_sensor.rest/)
- [Ping (ICMP) en Home Assistant](https://www.home-assistant.io/integrations/ping/)
