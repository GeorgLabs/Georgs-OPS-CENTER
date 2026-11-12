"""Creates .env with a fresh random secret key (only if it does not exist yet)."""

import secrets
from pathlib import Path

env = Path(__file__).resolve().parent.parent / ".env"
if env.exists():
    print(".env exists - leaving it alone.")
else:
    env.write_text(f"OPS_SECRET_KEY={secrets.token_urlsafe(48)}\nOPS_DEV=1\n", encoding="utf-8")
    print("Created .env with a new random secret key. Never share or commit this file.")
