#!/usr/bin/env python3
"""Resolve the latest stable ASM3 release to an immutable, checksummed source."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REPO = "sheltermanager/asm3"


def request(url):
    headers = {"User-Agent": "asm3-yunohost-updater", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    # Envía las credenciales solo a la API de GitHub.
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120)


def api(path):
    with request(f"https://api.github.com/repos/{REPO}/{path}") as response:
        return json.load(response)


def normalize_version(tag):
    if not re.fullmatch(r"v?\d+(?:[.-]\d+)*", tag):
        raise ValueError(f"Unexpected stable release tag: {tag!r}")
    return tag.removeprefix("v").replace("-", ".")


def resolve_release():
    release = api("releases/latest")
    if release["draft"] or release["prerelease"]:
        raise ValueError("Refusing draft or prerelease")
    tag = release["tag_name"]
    version = normalize_version(tag)
    obj = api(f"git/ref/tags/{tag}")["object"]
    for _ in range(8):
        if obj["type"] == "commit":
            break
        if obj["type"] != "tag":
            raise ValueError("Unexpected Git object")
        obj = api(f"git/tags/{obj['sha']}")["object"]
    else:
        raise ValueError("Too many nested annotated tags")
    commit = obj["sha"]
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Invalid commit hash")
    url = f"https://codeload.github.com/{REPO}/tar.gz/{commit}"
    digest = hashlib.sha256()
    with request(url) as archive:
        for chunk in iter(lambda: archive.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"repository": REPO, "channel": "stable", "tag": tag, "version": version,
            "commit": commit, "url": url, "sha256": digest.hexdigest()}


def update_manifest(text, previous, current):
    # Limita los reemplazos a la fuente principal para conservar otros recursos.
    start = text.index("    [resources.sources.main]")
    end = text.index("\n    [resources.", start + 1)
    block = text[start:end]
    block, count = re.subn(r'(?m)^    url = ".*"$', f'    url = "{current["url"]}"', block)
    if count != 1:
        raise ValueError("Expected exactly one main source URL")
    block, count = re.subn(r'(?m)^    sha256 = ".*"$', f'    sha256 = "{current["sha256"]}"', block)
    if count != 1:
        raise ValueError("Expected exactly one main checksum")
    text = text[:start] + block + text[end:]
    current_package = re.search(r'(?m)^version = "([^"~]+)~ynh(\d+)"$', text)
    if not current_package:
        raise ValueError("Missing package version")
    revision = int(current_package[2]) + 1 if current_package[1] == current["version"] else 1
    package_version = f'{current["version"]}~ynh{revision}'
    text = text[:current_package.start()] + f'version = "{package_version}"' + text[current_package.end():]
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Exit 1 if a new stable source exists; do not write")
    args = parser.parse_args()
    previous = json.loads((ROOT / "upstream.lock.json").read_text())
    current = resolve_release()
    if current == previous:
        print(f'ASM3 {current["tag"]}: already current ({current["commit"][:12]})')
        return
    if args.check:
        print(f'New ASM3 release: {current["tag"]} ({current["commit"][:12]})')
        raise SystemExit(1)
    manifest = ROOT / "manifest.toml"
    text = update_manifest(manifest.read_text(), previous, current)
    # Valida ambos contenidos antes de escribirlos.
    import tomllib
    tomllib.loads(text)
    manifest.write_text(text)
    (ROOT / "upstream.lock.json").write_text(json.dumps(current, indent=2) + "\n")
    print(f'Prepared ASM3 {current["tag"]}, SHA-256 {current["sha256"]}')


if __name__ == "__main__":
    main()
