"""Database plumbing. Endpoints never create their own connection - they ask for a Session:

    def my_endpoint(session: SessionDep): ...

That one habit is what makes the app testable (tests swap `get_session` for a fake database).
"""

from collections.abc import Iterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from app.config import get_settings


def make_engine(url: str, **kwargs) -> Engine:
    is_sqlite = url.startswith("sqlite")
    engine = create_engine(
        url, connect_args={"check_same_thread": False} if is_sqlite else {}, **kwargs
    )
    if is_sqlite:

        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _record):
            # SQLite ignores foreign keys unless you ask. We ask.
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
