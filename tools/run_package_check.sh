#!/bin/bash
# Ejecuta en un laboratorio Incus/LXD aislado de producción.
set -euo pipefail
cd "$(dirname "$0")/.."
package_root=$PWD
work_dir=${ASM3_PACKAGE_CHECK_DIR:-$package_root/.package-check}
mkdir -p "$work_dir/results"
# Prueba el contenido distribuible sin discos locales, copias de la herramienta,
# cachés ni credenciales. package_check copia incluso los archivos ignorados por Git.
bash tools/build_release.sh
version=$(python3 -c 'import tomllib; print(tomllib.load(open("manifest.toml", "rb"))["version"])')
source_dir=$(mktemp -d "$work_dir/source.XXXXXX")
git clone --quiet "$package_root/dist/asm3_ynh-$version.bundle" "$source_dir"
if [ ! -d "$work_dir/upstream/.git" ]; then
    git clone https://github.com/YunoHost/package_check.git "$work_dir/upstream"
fi
work_dir=$(realpath "$work_dir")
export WORKER_ID=${WORKER_ID:-0}
if command -v incus >/dev/null && [ "${YNHDEV_BACKEND:-incus}" = incus ]; then
    dist=${DIST:-bookworm}
    branch=${YNH_BRANCH:-stable}
    arch=${ARCH:-$(dpkg --print-architecture)}
    legacy_alias="yunohost-$dist-$branch-appci"
    # El repositorio oficial separa los alias con barras.
    # package_check busca este alias local con el formato anterior.
    if ! incus image info "$legacy_alias" >/dev/null 2>&1; then
        if ! incus remote list --format json | python3 -c 'import json,sys; sys.exit("yunohost" not in json.load(sys.stdin))'; then
            incus remote add yunohost https://repo.yunohost.org/incus --protocol simplestreams --public
        fi
        incus image copy "yunohost:yunohost/$dist-$branch/appci/$arch" local: --alias "$legacy_alias"
    fi
fi
status=0
rm -f "$work_dir/results/results_$WORKER_ID.json"
"$work_dir/upstream/package_check.sh" "$source_dir" "$@" > >(tee "$work_dir/results/console.log") 2>&1 || status=$?
for file in "results_$WORKER_ID.json" "full_log_$WORKER_ID.log" "summary_$WORKER_ID.png"; do
    if [ -f "$work_dir/upstream/$file" ]; then
        cp "$work_dir/upstream/$file" "$work_dir/results/"
    fi
done
git -C "$work_dir/upstream" rev-parse HEAD > "$work_dir/results/package-check-commit.txt"
if [ "$status" -ne 0 ]; then exit "$status"; fi
# El lanzador oficial puede terminar con 0 aunque falle algún escenario.
python3 - "$work_dir/results/results_$WORKER_ID.json" <<'PY'
import json, sys
from pathlib import Path
p = Path(sys.argv[1])
if not p.exists():
    raise SystemExit("package_check did not produce its structured results")
data = json.loads(p.read_text())
if not data.get('tests'):
    raise SystemExit("package_check reported no tests")
failed = [t for t in data['tests'] if t['main_result'] != 'success']
for t in data['tests']:
    print(f"{t['test_type']} {t.get('test_arg', '')}: {t['main_result']}")
if failed:
    raise SystemExit(f"{len(failed)} package_check test(s) failed; inspect the retained logs")
if int(data.get('level', 0)) == 0:
    raise SystemExit("All listed tests passed, but the official quality level is 0. Inspect the linter/catalog findings; this wrapper does not turn that result into a green quality check.")
PY
