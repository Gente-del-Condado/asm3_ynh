#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
package_root=$PWD
version=$(python3 -c 'import tomllib; print(tomllib.load(open("manifest.toml", "rb"))["version"])')
mkdir -p dist
tar --exclude='__pycache__' --exclude='*.pyc' -czf "dist/asm3_ynh-${version}.tar.gz" \
    manifest.toml upstream.lock.json tests.toml config_panel.toml scripts conf patches hooks doc docs tools tests .github .forgejo README.md AGENTS.md CONTRIBUTING.md LICENSE .gitignore
(cd dist && sha256sum "asm3_ynh-${version}.tar.gz") > "dist/asm3_ynh-${version}.tar.gz.sha256"
# Crea un bundle autocontenido a partir del contenido que se instala.
staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT
tar -xzf "dist/asm3_ynh-${version}.tar.gz" -C "$staging"
git -C "$staging" init --quiet --template= --initial-branch=main
git -C "$staging" add .
git -C "$staging" -c user.name='ASM3 YunoHost Packaging' -c user.email='packaging@localhost' \
    commit --quiet -m "Prepare ASM3 ${version} for YunoHost"
git -C "$staging" bundle create "$package_root/dist/asm3_ynh-${version}.bundle" --all
(cd dist && sha256sum "asm3_ynh-${version}.bundle") > "dist/asm3_ynh-${version}.bundle.sha256"
echo "dist/asm3_ynh-${version}.tar.gz"
echo "dist/asm3_ynh-${version}.bundle"
