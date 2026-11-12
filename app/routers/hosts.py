"""M2 - Hosts and their metrics, stored with SQLModel. M3/M4 lock it down:
M3: every endpoint here needs a login - add `user: CurrentUser` (already imported below).
M4: logged in is not the same as allowed - think about whose data this is.

Pattern for every endpoint: take a `session: SessionDep`, query with `select(...)`,
return a Pydantic schema (never the table object itself).
"""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query, Response
from sqlmodel import Session, col, select

from app.apikeys import hash_api_key, new_api_key
from app.config import get_settings
from app.db import SessionDep
from app.models import Host, Metric, utcnow
from app.schemas import HostCreate, HostCreated, HostPublic, MetricPublic
from app.security import CurrentUser

#@@ solution
#@@ stub
#| from app.todo import todo
#@@ end

router = APIRouter(prefix="/api/hosts", tags=["hosts"])

#@@ solution


def _to_public(host: Host, session: Session) -> HostPublic:
    """Host + its newest metric -> what the dashboard shows (N+1 queries: fine at this size)."""
    latest = session.exec(
        select(Metric)
        .where(Metric.host_id == host.id)
        .order_by(col(Metric.ts).desc(), col(Metric.id).desc())
        .limit(1)
    ).first()
    if latest is None:
        status = "unknown"
    else:
        window = timedelta(seconds=get_settings().online_window_seconds)
        status = "online" if utcnow() - latest.ts <= window else "offline"
    return HostPublic(
        id=host.id,  # type: ignore[arg-type]
        name=host.name,
        description=host.description,
        created_at=host.created_at,
        status=status,
        last_seen=latest.ts if latest else None,
        cpu_percent=latest.cpu_percent if latest else None,
        memory_percent=latest.memory_percent if latest else None,
        disk_percent=latest.disk_percent if latest else None,
    )


def _get_own_host(session: Session, host_id: int, user) -> Host:
    """404 - not 403 - for hosts that are not yours: do not even confirm that they exist."""
    host = session.exec(
        select(Host).where(Host.id == host_id, Host.owner_id == user.id)
    ).first()
    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")
    return host


@router.post("", status_code=201, response_model=HostCreated)
def create_host(data: HostCreate, session: SessionDep, user: CurrentUser):
    key = new_api_key()
    host = Host(
        name=data.name,
        description=data.description,
        api_key_hash=hash_api_key(key),  # we store the hash; the key itself is shown once
        owner_id=user.id,
    )
    session.add(host)
    session.commit()
    session.refresh(host)
    return HostCreated(
        id=host.id,  # type: ignore[arg-type]
        name=host.name,
        description=host.description,
        created_at=host.created_at,
        api_key=key,
    )


@router.get("", response_model=list[HostPublic])
def list_hosts(
    session: SessionDep,
    user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    q: str | None = Query(None, max_length=50),
):
    stmt = select(Host).where(Host.owner_id == user.id)
    if q:
        # autoescape: a "%" typed by the user is a plain character, not a LIKE wildcard
        stmt = stmt.where(col(Host.name).icontains(q, autoescape=True))
    hosts = session.exec(stmt.order_by(col(Host.id)).offset(skip).limit(limit)).all()
    return [_to_public(h, session) for h in hosts]


@router.get("/{host_id}", response_model=HostPublic)
def get_host(host_id: int, session: SessionDep, user: CurrentUser):
    return _to_public(_get_own_host(session, host_id, user), session)


@router.get("/{host_id}/metrics", response_model=list[MetricPublic])
def host_metrics(
    host_id: int,
    session: SessionDep,
    user: CurrentUser,
    minutes: int = Query(60, ge=1, le=1440),
    limit: int = Query(500, ge=1, le=5000),
):
    host = _get_own_host(session, host_id, user)
    since = utcnow() - timedelta(minutes=minutes)
    rows = session.exec(
        select(Metric)
        .where(Metric.host_id == host.id, Metric.ts >= since)
        .order_by(col(Metric.ts).desc(), col(Metric.id).desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))  # newest `limit` rows, oldest first (nice for charts)


@router.delete("/{host_id}", status_code=204)
def delete_host(host_id: int, session: SessionDep, user: CurrentUser):
    host = _get_own_host(session, host_id, user)
    session.delete(host)  # its metrics go with it (cascade)
    session.commit()
    return Response(status_code=204)
#@@ stub
#|
#|
#| # Tip: write one helper that turns a Host (+ its newest Metric) into a HostPublic,
#| # and use it in every endpoint below.
#|
#|
#| @router.post("", status_code=201, response_model=HostCreated)
#| def create_host(data: HostCreate) -> HostCreated:
#|     """TODO M2 - create a host.
#|
#|     Make a key with new_api_key(), store ONLY hash_api_key(key) in Host.api_key_hash, save the host,
#|     and answer 201 with HostCreated - the plain key is returned this one time and never again.
#|     (You need a database session: add `session: SessionDep` as a parameter.)
#|     """
#|     todo("M2", "POST /api/hosts")
#|
#|
#| @router.get("", response_model=list[HostPublic])
#| def list_hosts() -> list[HostPublic]:
#|     """TODO M2 - list hosts, oldest first, as HostPublic.
#|
#|     Query parameters: skip (>= 0, default 0), limit (1..100, default 50),
#|     q (optional text, at most 50 characters: only hosts whose name CONTAINS q, ignoring capitals).
#|     status: "unknown" if the host never reported, "online" if its newest metric is younger than
#|     get_settings().online_window_seconds, otherwise "offline". last_seen / cpu / memory / disk
#|     come from the newest metric (None when there is none).
#|     """
#|     todo("M2", "GET /api/hosts")
#|
#|
#| @router.get("/{host_id}", response_model=HostPublic)
#| def get_host(host_id: int) -> HostPublic:
#|     """TODO M2 - one host. Unknown id -> HTTP 404 with detail "Host not found"."""
#|     todo("M2", "GET /api/hosts/{id}")
#|
#|
#| @router.get("/{host_id}/metrics", response_model=list[MetricPublic])
#| def host_metrics(host_id: int) -> list[MetricPublic]:
#|     """TODO M2 - the measurements of one host, OLDEST FIRST (that is what charts want).
#|
#|     Query parameters: minutes (1..1440, default 60) = how far back, limit (1..5000, default 500)
#|     = at most that many - when there are more, keep the NEWEST ones. Unknown host -> 404.
#|     """
#|     todo("M2", "GET /api/hosts/{id}/metrics")
#|
#|
#| @router.delete("/{host_id}", status_code=204)
#| def delete_host(host_id: int) -> Response:
#|     """TODO M2 - delete a host and, with it, all its metrics. Answer 204 without a body.
#|     Unknown id -> 404 "Host not found". Afterwards the host's API key must stop working."""
#|     todo("M2", "DELETE /api/hosts/{id}")
#@@ end
