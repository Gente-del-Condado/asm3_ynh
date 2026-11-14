"""Prepara la versión, los informes y el esquema del editor SQL sin npm."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def build(root):
    root = Path(root).resolve()
    version = (root / "VERSION").read_text().strip()
    if not re.fullmatch(r"[0-9]+(?:[.\-][0-9]+)*u?", version):
        raise ValueError("La versión del código de ASM3 no tiene el formato esperado")
    print("Preparando los datos de versión y el catálogo local de informes de ASM3…", flush=True)
    version_file = root / "src/asm3/__version__.py"
    version_file.write_text(
        f"VERSION = {json.dumps(version)}\nBUILD = {json.dumps(version)}\n"
    )
    # El archivo de origen verificado también incluye la colección de informes.
    reports = root / "reports"
    (reports / "reports.txt").write_text(
        "&&&\n".join(p.read_text() for p in sorted(reports.glob("*.rep")))
    )
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("ASM3_YNH_MAINTENANCE_LOG", None)
    print("Preparando el esquema SQLite temporal del editor SQL de ASM3…", flush=True)
    subprocess.run(
        [sys.executable, "scripts/schema/make_db.py"], cwd=root,
        env={**env, "ASM3_YNH_MAINTENANCE_LOG": "1"}, check=True,
    )
    # schema.py escribe JavaScript por stdout. Mantén sus diagnósticos en stderr.
    print("Generando los recursos del editor SQL de ASM3…", flush=True)
    bundle = root / "src/static/js/bundle"
    bundle.mkdir(parents=True, exist_ok=True)
    with (bundle / "schema.js").open("w") as output:
        subprocess.run([sys.executable, "scripts/schema/schema.py"], cwd=root, env=env, stdout=output, check=True)
    (root / "scripts/schema/schema.db").unlink()
    print("Recursos de ASM3 preparados; esquema SQLite temporal retirado.", flush=True)


if __name__ == "__main__":
    build(sys.argv[1])
