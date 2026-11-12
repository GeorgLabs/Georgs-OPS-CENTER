"""M2 - where the agents report in. Machines authenticate with an API key, not a login."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import APIKeyHeader
from sqlmodel import select

from app.apikeys import hash_api_key
from app.db import SessionDep
from app.models import Host, Metric
from app.schemas import MetricIn, MetricPublic

from app.todo import todo

router = APIRouter(prefix="/api", tags=["agents"])

# `auto_error=False` -> we raise the 401 ourselves, so a missing key and a wrong key look the same.
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_agent_host(key: Annotated[str | None, Depends(api_key_header)], session: SessionDep) -> Host:
    """TODO M2 - which host does this API key belong to?

    No key, or a key that matches no host -> HTTP 401 (headers={"WWW-Authenticate": "ApiKey"}).
    Look the host up by hash_api_key(key).
    """
    #todo("M2", "get_agent_host")
    if key is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    host = session.exec(
        select(Host)
        .where(Host.api_key_hash==hash_api_key(key))
    ).first()
    if host is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return host


@router.post("/ingest", status_code=201, response_model=MetricPublic)
def ingest(
    data: MetricIn,
    host: Annotated[Host, Depends(get_agent_host)],
    session: SessionDep,
):
    """TODO M2 - store one measurement for the host that owns the key. Answer 201 with the
    stored measurement (MetricPublic). The body never says WHICH host - the key decides."""
    #todo("M2", "POST /api/ingest")
    metric = Metric(
        host_id=host.id,
        **data.model_dump() 
    )
    session.add(metric)
    session.commit()
    zwoetui = MetricPublic(
        ts=metric.ts,
        cpu_percent=data.cpu_percent,
        memory_percent=data.memory_percent,
        disk_percent=data.disk_percent
    )
    session.refresh(metric)
    return zwoetui