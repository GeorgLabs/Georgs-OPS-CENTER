"""Dev-only routes (OPS_DEV=1): traffic feed and Mission Control. Never reachable from the network."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.dev import mission, traffic

BOOT_ID = secrets.token_hex(4)  # changes whenever the server restarts (= after you save a file)
_LOCAL = {"127.0.0.1", "::1", "localhost", "testclient"}


def loopback_only(request: Request) -> None:
    """Even if someone starts the server with --host 0.0.0.0 by accident, dev tools stay local."""
    if not request.client or request.client.host not in _LOCAL:
        raise HTTPException(status_code=404)


router = APIRouter(
    prefix="/_dev", include_in_schema=False, dependencies=[Depends(loopback_only)]
)


@router.get("/info")
def info() -> dict:
    return {"boot_id": BOOT_ID}


@router.get("/traffic")
def traffic_feed(after: int = Query(0, ge=0)) -> dict:
    return traffic.snapshot(after)


@router.post("/mission/run")
def run_mission() -> dict:
    return mission.run_all()
