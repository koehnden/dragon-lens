import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routers import api_keys, metrics, tracking, verticals
from config import settings
from models import init_db
from services.brand_recognition import OLLAMA_EMBEDDING_MODEL, ENABLE_EMBEDDING_CLUSTERING

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    init_db()
    if ENABLE_EMBEDDING_CLUSTERING:
        logger.info(f"Using Ollama embedding model: {OLLAMA_EMBEDDING_MODEL}")
        logger.info("Ensure model is pulled with: ollama pull qllama/bge-small-zh-v1.5")
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
app.include_router(api_keys.router, prefix="/api/v1", tags=["api-keys"])


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
