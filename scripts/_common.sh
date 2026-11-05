#!/bin/bash
# YunoHost injects these variables; url_path is consumed by its template helper.
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

asm3_configure() {
    asm3_url_path
    set +x
    ynh_app_setting_set_default --key=proxy_secret --value="$(ynh_string_random --length=64)"
    ynh_app_setting_set_default --key=rescue_password --value="$(ynh_string_random --length=48)"
    ynh_config_add --template=asm3.conf --destination="$install_dir/asm3.conf"
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

asm3_sources() {
    ynh_setup_source --dest_dir="$install_dir/upstream" --full_replace
    mkdir -p "$install_dir/ynh"
    cp ../conf/{server,build,manage,manage_oidc}.py "$install_dir/ynh/"
    cp ../conf/ynh_{auth,oidc}.py "$install_dir/upstream/src/"
    # Build as root before making application code read-only to the service.
    ASM3_CONF="$install_dir/asm3.conf" python3 "$install_dir/ynh/build.py" "$install_dir/upstream"
    chown -R "root:$app" "$install_dir"
    chmod -R u=rwX,g=rX,o= "$install_dir"
    # Nginx proxies all requests; no web-server access to source or credentials.
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
    ynh_die "ASM3 did not become ready on its local port"
}
