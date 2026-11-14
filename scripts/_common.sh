#!/bin/bash
# YunoHost inyecta estas variables. Su helper de plantillas usa url_path.
# shellcheck disable=SC2154,SC2034

asm3_lock() {
    mkdir -p "$data_dir/cache"
    chown "$app:$app" "$data_dir" "$data_dir/cache"
    chmod 750 "$data_dir" "$data_dir/cache"
    touch "$data_dir/maintenance.lock"
    chown "$app:$app" "$data_dir/maintenance.lock"
    chmod 600 "$data_dir/maintenance.lock"
    exec 9>"$data_dir/maintenance.lock"
    flock -w 300 9
}

asm3_url_path() {
    url_path="${path%/}"
}

# Los helpers de configuración pueden mostrar diffs antes de que YunoHost oculte los valores.
# Filtra las líneas con credenciales antes de enviarlas a consola o a los registros.
asm3_redact_config_log() {
    python3 -u -c 'import re,sys
for line in sys.stdin:
    if re.search(r"password|passwd|passphrase|secret|token|db_pass|smtp_pass",line,re.I):
        sys.stdout.write("[redacted configuration line]\n")
    else:
        sys.stdout.write(line)'
}

asm3_safe_config() (
    set +x
    set -o pipefail
    "$@" 2>&1 | asm3_redact_config_log
)

asm3_configure() {
    asm3_url_path
    set +x
    ynh_app_setting_set_default --key=proxy_secret --value="$(ynh_string_random --length=64)"
    ynh_app_setting_set_default --key=rescue_password --value="$(ynh_string_random --length=48)"
    asm3_safe_config ynh_config_add --template=asm3.conf --destination="$install_dir/asm3.conf"
    chown "root:$app" "$install_dir/asm3.conf"
    chmod 640 "$install_dir/asm3.conf"
    if [ ! -e "$install_dir/oidc.json" ]; then
        cp ../conf/oidc.json.example "$install_dir/oidc.json"
    fi
    chown "root:$app" "$install_dir/oidc.json"
    chmod 640 "$install_dir/oidc.json"
    set -x
    ynh_config_add --template=cron --destination="/etc/cron.d/$app"
    chmod 644 "/etc/cron.d/$app"
    ynh_config_add_systemd
}

asm3_logo() {
    local logo_hash package_logo_hash
    logo_hash=$(yunohost user permission info "$app.main" --output-as=json |
        python3 -c 'import json,sys; print(json.load(sys.stdin).get("logo_hash") or "")') || return 1
    package_logo_hash=$(sha256sum "$install_dir/ynh/logo.png")
    package_logo_hash="${package_logo_hash%% *}"
    # Vuelve a registrar el predeterminado para restaurar también su PNG en otro servidor.
    # Conserva el logo que el administrador haya elegido para esta instancia.
    if [ -z "$logo_hash" ] || [ "$logo_hash" = "$package_logo_hash" ]; then
        yunohost user permission update "$app.main" --logo="$install_dir/ynh/logo.png"
    fi
}

asm3_sources() {
    mkdir -p "$install_dir/upstream"
    ynh_setup_source --dest_dir="$install_dir/upstream" --full_replace
    mkdir -p "$install_dir/ynh"
    cp ../conf/{server,build,manage,manage_oidc,manage_identity}.py "$install_dir/ynh/"
    cp ../conf/ynh_{auth,oidc,mfa}.py "$install_dir/upstream/src/"
    cp ../doc/logo.png "$install_dir/ynh/logo.png"
    # Genera los recursos como root antes de dejar el código en solo lectura para el servicio.
    ynh_print_info "Preparando el esquema SQLite temporal y los recursos del editor SQL de ASM3…"
    ASM3_CONF="$install_dir/asm3.conf" python3 "$install_dir/ynh/build.py" "$install_dir/upstream"
    chown -R "root:$app" "$install_dir"
    chmod -R u=rwX,g=rX,o= "$install_dir"
    if [ -f "$install_dir/identity_admin.json" ]; then
        chown root:root "$install_dir/identity_admin.json"
        chmod 600 "$install_dir/identity_admin.json"
    fi
    asm3_logo
    # Nginx reenvía las peticiones. No necesita acceso al código ni a las credenciales.
}

asm3_start() {
    ynh_systemctl --service="$app" --action=start
    local attempt
    for attempt in {1..60}; do
        if curl --fail --silent --output /dev/null "http://127.0.0.1:$port/_ynh_health"; then
            return 0
        fi
        sleep 1
    done
    journalctl -u "$app" -n 50 --no-pager >&2
    ynh_die "ASM3 no respondió a tiempo en su puerto local"
}

asm3_identity_reconcile() {
    set +x
    ASM3_CONF="$install_dir/asm3.conf" PYTHONDONTWRITEBYTECODE=1 python3 "$install_dir/ynh/manage_identity.py" reconcile --app "$app" --install-dir "$install_dir"
    set -x
}
