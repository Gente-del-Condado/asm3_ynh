#!/bin/bash
# Dependencies for disposable Debian/Ubuntu CI workers, not production hosts.
set -euo pipefail
script_path=$(realpath "$0")
cd "$(dirname "$0")/.."
if [ "$(id -u)" -ne 0 ]; then
    exec sudo bash "$script_path"
fi
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y python3 git curl ca-certificates patch shellcheck python3-jsonschema
mapfile -t packages < <(/usr/bin/python3 -c 'import tomllib; print("\n".join(tomllib.load(open("manifest.toml", "rb"))["resources"]["apt"]["packages"]))')
apt-get install -y "${packages[@]}"
