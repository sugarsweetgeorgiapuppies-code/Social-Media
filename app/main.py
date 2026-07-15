"""FastAPI application: API + static dashboard."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import STATIC_DIR, settings
from .database import init_db
from .logging_config import configure_logging, get_logger
from .routes.api import router as api_router
from .scheduler import shutdown_scheduler, start_scheduler

configure_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Starting %s...", settings.BUSINESS_NAME)
    init_db()
    if not settings.ai_enabled:
        log.warning(
            "No ANTHROPIC_API_KEY set — running in inferred (offline) mode. "
            "Add a key to enable live daily trend research."
        )
    start_scheduler()
    yield
    shutdown_scheduler()


app = FastAPI(
    title="Sugar Sweet Georgia Puppies — AI Social Media Employee",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/health")
def health():
    return {"status": "ok", "ai_enabled": settings.ai_enabled}


# Serve the dashboard. The static mount is added last so /api and /health win.
@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
