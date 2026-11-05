#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
export PYTHONDONTWRITEBYTECODE=1
/usr/bin/python3 tools/check_package.py
/usr/bin/python3 -m unittest discover -s tests -v
/usr/bin/python3 tools/smoke_test.py "$@"
bash tools/build_release.sh
