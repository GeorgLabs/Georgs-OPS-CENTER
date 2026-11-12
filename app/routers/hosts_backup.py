"""M2 - Hosts and their metrics, stored with SQLModel. M3/M4 lock it down:
M3: every endpoint here needs a login - add `user: CurrentUser` (already imported below).
M4: logged in is not the same as allowed - think about whose data this is.

Pattern for every endpoint: take a `session: SessionDep`, query with `select(...)`,
return a Pydantic schema (never the table object itself).
"""

from datetime import timedelta

from fastapi import APIRouter, HTTPException, Query, Response, Depends
from sqlmodel import Session, col, select

from app.apikeys import hash_api_key, new_api_key
from app.config import get_settings
from app.db import SessionDep, get_session
from app.models import Host, Metric, utcnow
from app.schemas import HostCreate, HostCreated, HostPublic, MetricPublic
from app.security import CurrentUser

from app.todo import todo

router = APIRouter(prefix="/api/hosts", tags=["hosts"])



# Tip: write one helper that turns a Host (+ its newest Metric) into a HostPublic,
# and use it in every endpoint below.


@router.post("", status_code=201, response_model=HostCreated)
def create_host(data: HostCreate, session: SessionDep, user: CurrentUser) -> HostCreated:
    """TODO M2 - create a host.

    Make a key with new_api_key(), store ONLY hash_api_key(key) in Host.api_key_hash, save the host,
    and answer 201 with HostCreated - the plain key is returned this one time and never again.
    (You need a database session: add `session: SessionDep` as a parameter.)
    """
    #todo("M2", "POST /api/hosts")
    key = new_api_key()

    host = Host(
        name=data.name,
        description=data.description,
        api_key_hash=hash_api_key(key),
        owner_id=user.id
    )

    session.add(host)
    session.commit()
    session.refresh(host)

    return HostCreated(
        id=host.id,
        name=host.name,
        description=host.description,
        created_at=host.created_at,
        api_key=key
    )
    


@router.get("", response_model=list[HostPublic])
def list_hosts(user: CurrentUser, session: SessionDep, skip: int = Query(default=0,ge=0), limit: int = Query(default=50, ge=1, le=100), q: str = Query(default="", max_length=50)) -> list[HostPublic]:
    """TODO M2 - list hosts, oldest first, as HostPublic.

    Query parameters: skip (>= 0, default 0), limit (1..100, default 50),
    q (optional text, at most 50 characters: only hosts whose name CONTAINS q, ignoring capitals).
    status: "unknown" if the host never reported, "online" if its newest metric is younger than
    get_settings().online_window_seconds, otherwise "offline". last_seen / cpu / memory / disk
    come from the newest metric (None when there is none).
    """
    #todo("M2", "GET /api/hosts")

    hosts = session.exec(
        select(Host)
        .where(col(Host.name).ilike(f"%{q}%"))
        .order_by(Host.created_at)
        .offset(skip)
        .limit(limit)
    ).all()

    result = []

    for host in hosts:
        metric = session.exec(
            select(Metric)
            .where(Metric.host_id == host.id)
            .order_by(Metric.ts.desc())
        ).first()

        if host.owner_id is not user.id and not user.is_admin:
            continue
        if metric is None:
            status = "unknown"
        elif (utcnow() - metric.ts).total_seconds() < get_settings().online_window_seconds:
            status = "online"
        else:
            status = "offline"

        result.append(
            HostPublic(
                id=host.id,
                name=host.name,
                description=host.description,
                created_at=host.created_at,
                status=status,
                last_seen=metric.ts if metric else None,
                cpu_percent=metric.cpu_percent if metric else None,
                memory_percent=metric.memory_percent if metric else None,
                disk_percent=metric.disk_percent if metric else None
            )
        )

    return result

'''
@router.get("/{host_id}", response_model=HostPublic)
def get_host(host_id: int, session: SessionDep) -> HostPublic:
    """TODO M2 - one host. Unknown id -> HTTP 404 with detail "Host not found"."""
    #todo("M2", "GET /api/hosts/{id}")


    host: Host = session.exec(
        select(Host).where(Host.id==host_id)
    ).first()
    if host == None:
        raise HTTPException(status_code=404, detail="Host not found")

    metric = session.exec(
        select(Metric)
        .where(Metric.host_id == host.id)
    ).first()

    last_seen = None





    if metric is None:
        status = "unknown"
        cpu_percent = None
        memory_percent = None
        disk_percent = None
    elif (utcnow() - metric.ts).total_seconds() < get_settings().online_window_seconds:
        status = "online"
        last_seen = metric.ts
        cpu_percent = metric.cpu_percent
        memory_percent = metric.memory_percent
        disk_percent = metric.disk_percent
    else:
        status = "offline"
        last_seen = metric.ts
        cpu_percent = metric.cpu_percent
        memory_percent = metric.memory_percent
        disk_percent = metric.disk_percent

    baasf = HostPublic(
        id = host.id,
        name = host.name,
        description=host.description,
        created_at=host.created_at,
        status=status,
        last_seen=last_seen,
        cpu_percent=cpu_percent,
        memory_percent=memory_percent,
        disk_percent=disk_percent
    )

    return baasf
'''





@router.get("/{host_id}", response_model=HostPublic)
def get_host(host_id: int, session: SessionDep, user: CurrentUser) -> HostPublic:

    host = session.exec(
        select(Host).where(Host.id == host_id)
    ).first()

    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")

    if host.owner_id is not user.id and not user.is_admin:
        raise HTTPException(status_code=404, detail="Host not found")

    metric = session.exec(
        select(Metric)
        .where(Metric.host_id == host.id)
        .order_by(Metric.ts.desc(), Metric.id.desc())
    ).first()

    if metric is None:
        status = "unknown"
    elif (utcnow() - metric.ts).total_seconds() < get_settings().online_window_seconds:
        status = "online"
    else:
        status = "offline"

    return HostPublic(
        id=host.id,
        name=host.name,
        description=host.description,
        created_at=host.created_at,
        status=status,
        last_seen=metric.ts if metric else None,
        cpu_percent=metric.cpu_percent if metric else None,
        memory_percent=metric.memory_percent if metric else None,
        disk_percent=metric.disk_percent if metric else None
    )





@router.get("/{host_id}/metrics", response_model=list[MetricPublic])
def host_metrics(user: CurrentUser, host_id: int, session: SessionDep, minutes: int = Query(default=60, ge=1, le=1440), limit: int = Query(default=500, ge=1, le=5000)) -> list[MetricPublic]:
    """TODO M2 - the measurements of one host, OLDEST FIRST (that is what charts want).

    Query parameters: minutes (1..1440, default 60) = how far back, limit (1..5000, default 500)
    = at most that many - when there are more, keep the NEWEST ones. Unknown host -> 404.
    """
    #todo("M2", "GET /api/hosts/{id}/metrics")
    host = session.exec(
        select(Host).where(Host.id == host_id)
    ).first()

    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")

    if user.id is not host.owner_id and not user.is_admin:
        raise HTTPException(status_code=404, detail="Host not found")
    
    since = utcnow() - timedelta(minutes=minutes)

    metrics = session.exec(

        select(Metric)
        .where(
            Metric.host_id == host_id,
            Metric.ts >= since
        )
        .order_by(Metric.ts.desc(), Metric.id.desc())
        .limit(limit)
    ).all()

    metrics = list(reversed(metrics))
    return metrics


@router.delete("/{host_id}", status_code=204)
def delete_host(host_id: int, session: SessionDep, user: CurrentUser) -> Response:
    """TODO M2 - delete a host and, with it, all its metrics. Answer 204 without a body.
    Unknown id -> 404 "Host not found". Afterwards the host's API key must stop working."""
    #todo("M2", "DELETE /api/hosts/{id}")
    host = session.exec(
        select(Host)
        .where(
            Host.id == host_id
        )
    ).first()

    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")
    if host.owner_id is not user.id and not user.is_admin:
        raise HTTPException(status_code=404, detail="Host not found")

    session.delete(host)
    session.commit()

    return Response(status_code=204)