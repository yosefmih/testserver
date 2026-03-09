import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from config import config
from db import init_pool, close_pool, run_migrations
from routes.auth import router as auth_router
from routes.projects import router as projects_router
from routes.integrations import router as integrations_router
from routes.webhooks import router as webhooks_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting up, connecting to database")
    await init_pool(config.DATABASE_URL)
    await run_migrations()
    logger.info("Database ready, migrations applied")
    yield
    logger.info("Shutting down")
    await close_pool()


app = FastAPI(title="Linear Autopilot", lifespan=lifespan)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(projects_router, prefix="/api/v1", tags=["projects"])
app.include_router(integrations_router, prefix="/api/v1", tags=["integrations"])
app.include_router(webhooks_router, prefix="/webhooks", tags=["webhooks"])


@app.get("/health")
async def health():
    return {"status": "healthy"}


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="frontend")
