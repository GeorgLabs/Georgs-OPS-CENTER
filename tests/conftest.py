"""Shared test setup: every test gets a brand-new, empty in-memory database."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from app.db import get_session, make_engine
from app.main import create_app


@pytest.fixture
def engine():
    engine = make_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def client(engine):
    app = create_app(dev=False, migrate=False)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


@pytest.fixture
def auth_client(client):
    """A client that is registered and logged in."""
    body = {"username": "tester", "password": "correct-horse-battery"}
    client.post("/api/auth/register", json=body)
    token = client.post("/api/auth/token", data=body).json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"
    return client
