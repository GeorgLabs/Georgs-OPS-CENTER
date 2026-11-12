"""The application. `create_app()` assembles everything; `app` is what the server runs.

Start it with:   run.bat   (Windows)   or   ./run.sh      (both call `fastapi dev`)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import ROOT, get_settings
from app.middleware import SecurityHeadersMiddleware
from app.routers import admin, auth, hosts, ingest, system

STATIC = ROOT / "static"


def run_migrations() -> None:
    """Bring the database up to date (Alembic). Safe to run on every start."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    run_migrations()
    yield


def create_app(*, dev: bool | None = None, migrate: bool = True) -> FastAPI:
    """dev=None -> follow OPS_DEV. migrate=False is for tests and Mission Control (own database)."""
    settings = get_settings()
    dev = settings.dev if dev is None else dev

    app = FastAPI(
        title="Georgs Ops Center",
        version="0.1.0",
        docs_url=None,  # we serve our own copy of /docs below (works offline, no CDN)
        redoc_url=None,
        lifespan=lifespan if migrate else None,
    )
    app.add_middleware(SecurityHeadersMiddleware)

    if dev:
        from app.dev.routes import router as dev_router
        from app.dev.traffic import TrafficMiddleware

        app.add_middleware(TrafficMiddleware)
        app.include_router(dev_router)

        @app.get("/docs", include_in_schema=False)
        def swagger_ui():
            return get_swagger_ui_html(
                openapi_url="/openapi.json",
                title="Georgs Ops Center - API docs",
                swagger_js_url="/static/vendor/swagger-ui/swagger-ui-bundle.js",
                swagger_css_url="/static/vendor/swagger-ui/swagger-ui.css",
                swagger_favicon_url="/static/vendor/swagger-ui/favicon-32x32.png",
                oauth2_redirect_url=None,
            )

    for router in (system.router, hosts.router, ingest.router, auth.router, admin.router):
        app.include_router(router)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
