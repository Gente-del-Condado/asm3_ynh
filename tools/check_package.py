#!/usr/bin/env python3
"""Fast package checks; no YunoHost installation or network required."""
import ast
import json
from pathlib import Path
import re
import subprocess
import tomllib
import jsonschema

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = tomllib.loads((ROOT / "manifest.toml").read_text())
    jsonschema.validate(manifest, json.loads((ROOT / "tests/schemas/manifest.v2.schema.json").read_text()))
    lock = json.loads((ROOT / "upstream.lock.json").read_text())
    source = manifest["resources"]["sources"]["main"]
    assert source["url"] == lock["url"]
    assert source["sha256"] == lock["sha256"]
    assert re.fullmatch(r"[a-f0-9]{64}", lock["sha256"])
    assert lock["commit"] in source["url"]
    assert manifest["version"].startswith(lock["version"] + "~ynh")
    assert manifest["packaging_format"] == 2
    assert manifest["integration"]["helpers_version"] == "2.1"
    test_manifest = tomllib.loads((ROOT / "tests.toml").read_text())
    jsonschema.validate(test_manifest, json.loads((ROOT / "tests/schemas/tests.v1.schema.json").read_text()))
    panel = tomllib.loads((ROOT / "config_panel.toml").read_text())
    jsonschema.validate(panel, json.loads((ROOT / "tests/schemas/config_panel.v1.schema.json").read_text()))
    scripts = [str(p) for p in sorted((ROOT / "scripts").iterdir())]
    scripts += [str(p) for p in sorted((ROOT / "tools").glob("*.sh"))]
    scripts += [str(p) for p in sorted((ROOT / "hooks").iterdir())]
    for script in scripts:
        subprocess.run(["bash", "-n", script], check=True)
        assert Path(script).stat().st_mode & 0o111, f"Not executable: {script}"
    # YunoHost inyecta estas variables. Algunas las consume su motor de plantillas.
    subprocess.run(["shellcheck", "-S", "warning", "-e", "SC1091,SC2154,SC2034", *scripts], check=True)
    for directory in ("conf", "tools", "tests"):
        for file in (ROOT / directory).glob("*.py"):
            ast.parse(file.read_text(), filename=str(file))
    assert not any("FIXME" in p.read_text() for p in (ROOT / "scripts").iterdir())
    print("Package metadata, source lock, shell and Python syntax: OK")


if __name__ == "__main__":
    main()
