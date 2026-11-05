Open https://__DOMAIN____PATH__ through your YunoHost portal as **__ADMIN__**.
Native SSO creates staff profiles from LDAP. New staff have animal read-only access;
grant additional ASM3 roles as needed. The selected administrator has full access.

Restrict the **staff** permission to your staff. To publish adoption pages, forms
or API methods, allow visitors in the **main** permission and configure ASM3 services.

Local recovery: `/login?local=1`, user `ynh_rescue___APP__`.
As root, retrieve its password with `yunohost app setting __APP__ rescue_password`.
Do not share it or place it in logs. Default upstream accounts are disabled.

Set organisation, timezone and email in ASM3. Local authenticated SMTP is configured.
