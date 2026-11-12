"""M3 - Who are you? Passwords, login tokens and the "current user" dependency."""

from datetime import UTC, datetime, timedelta
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import OAuth2PasswordBearer
from pwdlib import PasswordHash

from app.config import get_settings
from app.db import SessionDep
from app.models import User

from sqlmodel import select

from app.todo import todo

# Argon2 - the current recommendation for storing passwords (slow on purpose, salted automatically).
password_hash = PasswordHash.recommended()

# A hash of a password nobody knows. Login checks it when the username does not exist, so
# "unknown user" and "wrong password" take the same time (see M4: user enumeration).
DUMMY_HASH = password_hash.hash("this-is-not-a-real-password")

# Makes the green "Authorize" button appear in /docs and tells FastAPI where to log in.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")


def unauthorized() -> HTTPException:
    return HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def hash_password(password: str) -> str:
    """TODO M3 - return the Argon2 hash of the password (see `password_hash` above)."""
    #todo("M3", "hash_password")
    pypasswd = password_hash.hash(password)
    #print(f"Passwort: pypasswd: {pypasswd}, password: {password}") 
    return pypasswd


def verify_password(plain: str, hashed: str) -> bool:
    """TODO M3 - True if `plain` matches the stored hash, otherwise False."""
    #todo("M3", "verify_password")
    return password_hash.verify(plain, hashed)


def create_access_token(user_id: int) -> str:
    """TODO M3 - a signed JWT for this user.

    Claims: "sub" = the user id AS TEXT, "iat" = now, "exp" = now + settings.access_token_minutes.
    Sign it with settings.secret_key (use .get_secret_value()) and settings.jwt_algorithm.
    Library: PyJWT -> jwt.encode(payload, key, algorithm=...)
    """
    #todo("M3", "create_access_token")
    settings = get_settings()
    now = datetime.now(UTC)
    exp = now + timedelta(minutes=settings.access_token_minutes)
    payload = {"sub": str(user_id), "iat": now, "exp": exp}
    tokenw = jwt.encode(payload=payload, key=settings.secret_key.get_secret_value(), algorithm=settings.jwt_algorithm)
    ##print(f"Access Token (tokenw): {tokenw}")
    return tokenw


def decode_access_token(token: str) -> int | None:
    """TODO M3 - the user id inside a valid token, or None if the token is NOT valid.

    "Valid" means: genuine signature, not expired, has "exp" and "sub", and "sub" is a number.
    Anything else -> None. It must never raise and never trust the token's own header:
    always pass algorithms=[settings.jwt_algorithm] to jwt.decode (a list - on purpose).
    """
    #todo("M3", "decode_access_token")
    settings = get_settings()
    try:
        tokend = jwt.decode(jwt=token, key=settings.secret_key.get_secret_value(), algorithms=[settings.jwt_algorithm], options={'require': ['exp', 'sub']})
        return int(tokend["sub"])
    except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
        ##print("decode failed:", type(exc).__name__, "-", exc)
        return None


def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], session: SessionDep) -> User:
    """TODO M3 - the logged-in user, or HTTP 401 (use unauthorized()).

    Steps: decode the token -> load that user from the database -> 401 if anything is missing.
    Endpoints use it like:  def my_endpoint(user: CurrentUser): ...
    """
    #todo("M3", "get_current_user")

    user_id = decode_access_token(token)
    #print(f"user_id in get current user: {user_id}")
    user = session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise unauthorized()
    ##print(f"User (user): {user}")
    return user


    # tokenw = decode_access_token(token)
    # user = session.exec(
    #     select(User)
    #     .where(
    #         User.id==tokenw
    #     )
    # ).first() if tokenw is not None else None

    # if user is None:
    #     raise unauthorized()

    # if user:
    #     return user
    # else:
    #     raise unauthorized()
    # return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_admin(user: CurrentUser) -> User:
    """TODO M3 - like get_current_user, but answers HTTP 403 "Admin only" for normal users."""
    #todo("M3", "require_admin")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin only")