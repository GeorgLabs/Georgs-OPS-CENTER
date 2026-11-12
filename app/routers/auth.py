"""M3 - registration, login and "who am I". M4 hardens the login."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app import ratelimit
from app.db import SessionDep
from app.models import User
from app.schemas import Token, UserCreate, UserPublic
from app.security import (
    DUMMY_HASH,
    CurrentUser,
    create_access_token,
    hash_password,
    verify_password,
)

import datetime


from app.todo import todo

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = logging.getLogger(__name__)

@router.post("/register", status_code=201, response_model=UserPublic)
def register(data: UserCreate, session: SessionDep):
    """TODO M3 - create a user.

    Usernames are not case sensitive: store them in lower case. A taken name -> HTTP 409.
    Store hash_password(...) - never the password. Answer 201 with UserPublic.
    (Read the schema UserCreate carefully before you trust it ...)
    """
    #todo("M3", "POST /api/auth/register")
    
    usernamew=data.username.lower()

    sessionw = session.exec(
        select(User)
        .where(
            User.username == usernamew
        )
    ).first()

    if sessionw:
        raise HTTPException(status_code=409)


    
    user = User(
            username=usernamew,
            hashed_password=hash_password(data.password)
            #is_admin=data.is_admin,
            #created_at=datetime.datetime.now(datetime.timezone.utc)   
        )

    session.add(user)
    session.commit()
    session.refresh(user)

    return user


@router.post("/token", status_code=200, response_model=Token)
def login(
    request: Request,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
    session: SessionDep
):
    """TODO M3 - log in. The body is a *form* (username, password), not JSON: that is the OAuth2
    standard, and it is what makes the "Authorize" button in /docs work.

    Right -> 200 with Token(access_token=create_access_token(user.id)).
    Wrong -> 401 with header WWW-Authenticate: Bearer.

    M4 (do it later, in this same function):
      * after 5 wrong attempts per (client address, username) in a minute -> 429 + Retry-After (ratelimit.py)
      * "no such user" and "wrong password" must be indistinguishable: same answer, same duration
        (verify against DUMMY_HASH when the user does not exist)
    """
    #todo("M3", "POST /api/auth/token")
    userlower = form.username.lower()
    #print(f"Username (userlower): {userlower}")

    key=(request.client.host if request.client else "?", userlower)
    wait = ratelimit.blocked_for(key)
    if wait:
        raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.", headers={"Retry-After": str(wait)})



    sessionw = session.exec(
        select(User)
        .where(
            User.username==userlower
        )
    ).first()



    #if not sessionw:
    #    raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"})

    
    #verifiedw = verify_password(form.password, sessionw.hashed_password)

    #Temp
    verifiedw = verify_password(form.password, sessionw.hashed_password if sessionw else DUMMY_HASH)
    #TempEnd
    if not verifiedw or sessionw is None:
        ratelimit.record_failure(key)
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Bearer"})

    tokenw = create_access_token(user_id=sessionw.id)


    ratelimit.reset(key)
    return Token(access_token=tokenw)
        



@router.get("/me", response_model=UserPublic)
def me(user: CurrentUser):
    """TODO M3 - the logged-in user (UserPublic). Without a valid token: 401."""
    #todo("M3", "GET /api/auth/me")

    logger.info(user)
    return user