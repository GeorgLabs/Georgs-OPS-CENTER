"""API keys for the agents (machines), as opposed to passwords for people.

A key is 256 random bits, so a plain SHA-256 is enough to store it safely: nobody can guess
or brute-force it. Passwords are different - people choose them, so they are guessable, and
need a deliberately slow hash (Argon2, see security.py). Know which one you need and why.
"""

import hashlib
import secrets

PREFIX = "ops_"


def new_api_key() -> str:
    return PREFIX + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()
