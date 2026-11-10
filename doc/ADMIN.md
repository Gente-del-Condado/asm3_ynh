## Operation

- URL: https://__DOMAIN____PATH__
- Administrator: `__ADMIN__` through the YunoHost portal. ASM3 retains application roles.
- Service: `systemctl status __APP__`; logs: `journalctl -u __APP__`.
- Config: `__INSTALL_DIR__/asm3.conf`, readable by root and the application group.
- Upstream code: `__INSTALL_DIR__/upstream`; WSGI adapter: `__INSTALL_DIR__/ynh`.
- Cache: `__DATA_DIR__/cache`. Persistent documents are in MariaDB, not the cache.
- Scheduled work: `/etc/cron.d/__APP__`; daily tasks and publishing at 03:17,
  email reports hourly at minute 23, in the server's timezone.

## Backups and upgrades

Use YunoHost backups to include code, package settings, service and proxy
configuration, database records, documents and images. Cache is disposable and not
backed up. Do not change `dbfs_store` to file storage: the package's backup policy
expects database storage. Large media collections make the SQL backup larger.

YunoHost creates a safety backup before upgrades and attempts restoration if an
upgrade fails. Retain independent backups. `--no-safety-backup` disables that
protection. The package serializes its batch jobs, schema migrations and backups
with an instance-specific lock.

Apply package updates through YunoHost. Configuration templates are regenerated on
upgrade and URL changes; use the ASM3 interface for application options. Review
YunoHost's copies of locally modified configuration files if you customize them.

## Access, public services and email

YunoHost's main permission gates every URL, including public services. Permit
visitors when external adopters or integrations must reach ASM3, then configure
ASM3's own permissions, service users and roles. Keep the separate `staff`
permission restricted to staff. Native YunoHost SSO checks LDAP on private requests;
new profiles start with animal read-only access. See [SSO.md](SSO.md). Each instance has its own DB, port, service, cache and cookie names.

Mail uses the app's local YunoHost SMTP credentials on 127.0.0.1:587 with STARTTLS. Check YunoHost
mail diagnosis, DNS, SPF/DKIM and mail availability for the domain. External
publishers, payment processors and S3 storage need your own accounts/settings.

## Uninstall

YunoHost removes the service, cron job, Nginx config, database, system user and
application code. `--purge` also removes the disposable data directory. Make a
backup before removal.

## Optional OpenID Connect

See [OIDC.md](OIDC.md). Configuration is `__INSTALL_DIR__/oidc.json`, root:__APP__ 0640.
Use `python3 __INSTALL_DIR__/ynh/manage_oidc.py --app __APP__ --config /root/oidc.json`.
OIDC is disabled until you register and configure your identity provider client.

## Dex and mandatory MFA

Every private login, including native SSO and local recovery, requires TOTP.
Enroll and confirm the factor at first login. Password APIs are disabled to
prevent a second-factor bypass. Public adoption forms and services stay available
according to ASM3 and YunoHost permissions.

Install Dex from the catalog and use the ASM3 YunoHost configuration panel to
configure Google, GitHub and Microsoft. Register the cloud clients yourself and
use the Dex callback displayed in the panel. Empty allowlists deny external access.
Only a YunoHost administrator/root can reset a lost MFA factor from this panel;
resetting invalidates existing and pending sessions. See [DEX.md](DEX.md).

## Monitoring from Home Assistant

The [Home Assistant guide](HOME_ASSISTANT.md) includes an optional REST monitor
for an instance that already permits visitors. Private instances can keep
their existing permissions and use server-level monitoring.
