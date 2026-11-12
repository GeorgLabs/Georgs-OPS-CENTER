"""M1 - Hello, data. Pydantic response models and query parameters, with real data from psutil.

Everything in this file works without a database. Try each endpoint in /docs while you build it.
"""

from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app import collectors

from app.security import CurrentUser
from app.todo import todo

router = APIRouter(prefix="/api", tags=["system"])


class SystemInfo(BaseModel):
    """TODO M1 - the shape of GET /api/system. Add these fields, with sensible limits:

    hostname: text              os: text                 cpu_count: whole number, at least 1
    cpu_percent, memory_percent, disk_percent: numbers from 0 to 100
    uptime_seconds: whole number, 0 or more
    """
    hostname: str = "GEORG_SRV_DEFAULT"
    cpu_count: int = Field(ge=1)
    cpu_percent: float = Field(ge=0, le=100)
    disk_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)
    os: str = "GEORGOS_DEFAULT"
    uptime_seconds: int

class sortTaskList(BaseModel):
    limit: int
    sort_by: str



class ProcessInfo(BaseModel):
    """TODO M1 - one process: pid (whole number), name (text),
    cpu_percent and memory_percent (numbers from 0 to 100)."""
    pid: int
    name: str
    cpu_percent: float = Field(ge=0, le=100)
    memory_percent: float = Field(ge=0, le=100)


@router.get("/health")
def health() -> dict:
    """TODO M1 - answer {"status": "ok"}. Your hello world. (No login needed, ever.)"""
    #todo("M1", "GET /api/health")
    return {"status": "ok"}


@router.get("/system", response_model=SystemInfo)
def system(user: CurrentUser) -> dict:
    """TODO M1 - return collectors.system_info(). FastAPI checks it against SystemInfo.

    (M3: this route will need a logged-in user: dependencies=[Depends(get_current_user)])
    """
    #todo("M1", "GET /api/system")
    return collectors.system_info()


@router.get("/system/processes", response_model=list[ProcessInfo])
def processes(user: CurrentUser, limit: int = Query(default=5, ge=1, le=25), sort_by: Literal["cpu", "memory", "name"] = Query(default="cpu")) -> list[dict]:
    """TODO M1 - the busiest processes, from collectors.list_processes().

    Query parameters (declare them as function arguments, FastAPI does the rest):
      limit    whole number, 1..25, default 5     -> how many processes to return (422 outside the range)
      sort_by  "cpu" | "memory" | "name", default "cpu"   (422 for anything else; use Literal)
    Order: cpu and memory highest first, name A-Z ignoring capitals.
    """
    #todo("M1", "GET /api/system/processes")
    #process = collectors.list_processes().sort(sortparameter.sort_by)[:sortparameter.limit]
    #return process

    process = collectors.list_processes()

    if sort_by == "cpu":
        process.sort(key=lambda p: p["cpu_percent"], reverse=True)

    elif sort_by == "memory":
        process.sort(key=lambda p: p["memory_percent"], reverse=True)

    elif sort_by == "name":
        process.sort(key=lambda p: p["name"].lower())

    return process[:limit]