"""Admin-only area. Provided - it only works once your `require_admin` (M3) does."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import col, select

from app.db import SessionDep
from app.models import User
from app.schemas import UserPublic
from app.security import require_admin

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/users", response_model=list[UserPublic])
def list_users(session: SessionDep, _admin: Annotated[User, Depends(require_admin)]):
    return session.exec(select(User).order_by(col(User.id))).all()
