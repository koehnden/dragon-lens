import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import metrics, tracking, verticals
from config import settings
from models import init_db
from services.brand_recognition import EMBEDDING_MODEL_NAME, ENABLE_EMBEDDING_CLUSTERING
from services.model_cache import ensure_embedding_model_available

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    init_db()
    if ENABLE_EMBEDDING_CLUSTERING:
        logger.info(f"Checking embedding model: {EMBEDDING_MODEL_NAME}")
        try:
            ensure_embedding_model_available(EMBEDDING_MODEL_NAME)
            logger.info(f"Embedding model {EMBEDDING_MODEL_NAME} is available")
        except Exception as e:
            logger.warning(f"Embedding model {EMBEDDING_MODEL_NAME} not available: {e}")
            logger.warning("Brand clustering will fall back to simpler methods")
    yield

app = FastAPI(
    title=settings.app_name,
    description="Track brand visibility in Chinese LLMs",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(verticals.router, prefix="/api/v1/verticals", tags=["verticals"])
app.include_router(tracking.router, prefix="/api/v1/tracking", tags=["tracking"])
app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["metrics"])


@app.get("/")
async def root():
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "status": "running",
    }


@app.get("/health")
async def health():
    return {"status": "healthy"}
