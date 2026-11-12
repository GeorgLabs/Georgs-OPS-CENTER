"""Alembic environment: points Alembic at our models and our database."""

from alembic import context
from sqlmodel import SQLModel

from app import models  # noqa: F401  (importing registers the tables on SQLModel.metadata)
from app.config import get_settings
from app.db import make_engine

target_metadata = SQLModel.metadata


def run_migrations_online() -> None:
    engine = make_engine(get_settings().database_url)
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # SQLite cannot ALTER most things; "batch" mode rebuilds tables
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Offline mode is not set up in this project.")
run_migrations_online()
