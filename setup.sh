#!/usr/bin/env sh
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
$PY -c 'import sys; sys.exit(0 if (3, 11) <= sys.version_info[:2] <= (3, 13) else 1)' || {
  echo "Needs Python 3.11-3.13 (3.13 is best). You have: $($PY --version)"; exit 1; }
[ -d .venv ] || $PY -m venv .venv
if [ -d wheelhouse ]; then
  .venv/bin/python -m pip install --no-index --find-links wheelhouse -r requirements.txt
else
  .venv/bin/python -m pip install -r requirements.txt
fi
.venv/bin/python scripts/init_env.py
echo "Done. Start it with ./run.sh"
