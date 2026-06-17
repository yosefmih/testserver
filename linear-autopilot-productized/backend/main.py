import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import config
from db import init_pool, close_pool, run_migrations
from routes.auth import router as auth_router
from routes.projects import router as projects_router
from routes.integrations import router as integrations_router
from routes.invites import router as invites_router, public_router as invites_public_router
from routes.webhooks import router as webhooks_router
from routes.internal import router as internal_router
from services.ticket_sync import ticket_sync_loop

logging.basicConfig(level=getattr(logging, config.LOG_LEVEL.upper(), logging.DEBUG), format="%(asctime)s %(levelname)s %(name)s %(message)s")
# Enable httpx request/response logging so sandbox API interactions are visible
logging.getLogger("httpx").setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.DEBUG))
logging.getLogger("httpcore").setLevel(getattr(logging, config.LOG_LEVEL.upper(), logging.DEBUG))
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up, connecting to database")
    await init_pool(config.DB_URL)
    await run_migrations()
    logger.info("Database ready, migrations applied")
    sync_task = asyncio.create_task(ticket_sync_loop())
    yield
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    logger.info("Shutting down")
    await close_pool()


app = FastAPI(title="Linear Autopilot", lifespan=lifespan)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(projects_router, prefix="/api/v1", tags=["projects"])
app.include_router(integrations_router, prefix="/api/v1", tags=["integrations"])
app.include_router(invites_router, prefix="/api/v1", tags=["invites"])
app.include_router(invites_public_router, prefix="/api/v1", tags=["invites"])
app.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])
app.include_router(internal_router, prefix="/api/internal", tags=["internal"])

from routes.integrations import callbacks_router
app.include_router(callbacks_router, prefix="/integrations", tags=["oauth-callbacks"])


@app.get("/health")
async def health():
    return {"status": "healthy"}


if STATIC_DIR.exists():
    assets_dir = STATIC_DIR / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="static-assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = STATIC_DIR / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(STATIC_DIR / "index.html")
