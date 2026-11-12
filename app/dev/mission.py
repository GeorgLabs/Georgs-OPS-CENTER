"""Mission Control: runs the probes (probes.py) against an isolated copy of YOUR app.

Nothing is stored and nothing is scored. Every probe is a small request-and-check that you can
read; the answer is simply "does your code do this right now?". Probes use their own in-memory
database, so they never touch your real data.
"""

import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel

from app.config import ROOT, get_settings
from app.db import get_session, make_engine
from app.dev import probes

MILESTONES = {
    "M1": "Hello, data",
    "M2": "Hosts & database",
    "M3": "Who are you?",
    "M4": "Red team",
}


def _where(exc: BaseException) -> str:
    """The innermost line of YOUR code (app/, not app/dev/) in the traceback."""
    app_dir, dev_dir = ROOT / "app", ROOT / "app" / "dev"
    found = ""
    for frame in traceback.extract_tb(exc.__traceback__):
        path = Path(frame.filename).resolve()
        if app_dir in path.parents and dev_dir not in path.parents:
            found = f"{path.relative_to(ROOT).as_posix()}:{frame.lineno}"
    return found


def run_all() -> dict:
    from app.main import create_app  # imported late: main.py imports the dev routes

    engine = make_engine("sqlite://", poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    app = create_app(dev=False, migrate=False)

    def override_session():
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = override_session
    ctx = probes.Ctx(app, engine, get_settings())

    started = time.perf_counter()
    results = []
    for p in probes.PROBES:
        status, message = "pass", ""
        try:
            p.fn(ctx)
        except probes.Todo as exc:
            status, message = "todo", str(exc)
        except AssertionError as exc:
            status, message = "fail", str(exc) or "check failed"
        except Exception as exc:  # noqa: BLE001 - whatever your code throws, we report it
            where = _where(exc)
            status = "fail"
            message = f"your code crashed - {type(exc).__name__}: {exc}" + (
                f"  (at {where})" if where else ""
            )
        results.append(
            {
                "id": p.id,
                "milestone": p.milestone,
                "title": p.title,
                "kind": p.kind,
                "status": status,
                "message": message,
            }
        )
    engine.dispose()

    milestones = []
    for mid, title in MILESTONES.items():
        mine = [r for r in results if r["milestone"] == mid]
        milestones.append(
            {
                "id": mid,
                "title": title,
                "total": len(mine),
                "passed": sum(r["status"] == "pass" for r in mine),
                "failed": sum(r["status"] == "fail" for r in mine),
                "todo": sum(r["status"] == "todo" for r in mine),
            }
        )
    return {
        "ran_at": datetime.now(UTC).isoformat(),
        "duration_ms": round((time.perf_counter() - started) * 1000),
        "milestones": milestones,
        "results": results,
    }
