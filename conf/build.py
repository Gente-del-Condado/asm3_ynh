"""Generate upstream's missing version module and SQL editor schema, without npm."""
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
        raise ValueError("Unexpected upstream VERSION")
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
    subprocess.run([sys.executable, "scripts/schema/make_db.py"], cwd=root, env=env, check=True)
    bundle = root / "src/static/js/bundle"
    bundle.mkdir(parents=True, exist_ok=True)
    with (bundle / "schema.js").open("w") as output:
        subprocess.run([sys.executable, "scripts/schema/schema.py"], cwd=root, env=env, stdout=output, check=True)
    (root / "scripts/schema/schema.db").unlink()


if __name__ == "__main__":
    build(sys.argv[1])
