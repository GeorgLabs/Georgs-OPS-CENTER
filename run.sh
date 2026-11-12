#!/usr/bin/env sh
cd "$(dirname "$0")"
[ -f .env ] || { echo "Run ./setup.sh first"; exit 1; }
echo "Ops Center: http://127.0.0.1:8000   (Ctrl+C stops it)"
exec .venv/bin/python -m fastapi dev --port 8000
