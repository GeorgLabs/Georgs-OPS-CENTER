"""What goes over the wire: request and response bodies (Pydantic).

Pydantic validates everything that comes in *before* your endpoint code runs,
so inside an endpoint you can trust the data.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

HostStatus = Literal["online", "offline", "unknown"]


# ---------------------------------------------------------------- hosts
class HostCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=50)
    description: str = Field(default="", max_length=200)


class HostPublic(BaseModel):
    """A host as the dashboard sees it. NEVER contains the API key."""

    id: int
    name: str
    description: str
    created_at: datetime
    status: HostStatus
    last_seen: datetime | None = None
    cpu_percent: float | None = None
    memory_percent: float | None = None
    disk_percent: float | None = None


class HostCreated(BaseModel):
    """Answer to POST /api/hosts - the only time the API key is ever shown."""

    id: int
    name: str
    description: str
    created_at: datetime
    api_key: str


# ---------------------------------------------------------------- metrics
class MetricIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    disk_percent: float = Field(ge=0, le=100)


class MetricPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    ts: datetime
    cpu_percent: float
    memory_percent: float
    disk_percent: float


# ---------------------------------------------------------------- users
class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    is_admin: bool = False  # handy: lets us create the very first admin straight from the API


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_admin: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 - the OAuth2 token *type*, not a secret
