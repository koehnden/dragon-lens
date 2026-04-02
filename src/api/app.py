import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routers import (
    admin,
    api_keys,
    consolidation,
    feedback,
    knowledge,
    metrics,
    tracking,
    verticals,
)
from config import settings
from models.knowledge_database import init_knowledge_db
from models.migrations import upgrade_db

logger = logging.getLogger(__name__)
MUTATING_METHODS = {"DELETE", "PATCH", "POST", "PUT"}


def _log_embedding_model_config() -> None:
    from services.brand_recognition.config import (
        ENABLE_EMBEDDING_CLUSTERING,
        OLLAMA_EMBEDDING_MODEL,
    )

    if ENABLE_EMBEDDING_CLUSTERING:
        logging.info("Using Ollama embedding model: %s", OLLAMA_EMBEDDING_MODEL)
        logging.info(
            "Ensure model is pulled with: ollama pull qllama/bge-small-zh-v1.5"
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    upgrade_db()
    init_knowledge_db()
    _log_embedding_model_config()
    yield


_log_embedding_model_config()


def create_app(
    app_lifespan=lifespan,
) -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        description="Track brand visibility in Chinese LLMs",
        version="0.1.0",
        lifespan=app_lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _add_public_demo_guard(app)
    _include_routers(app)
    _include_health_routes(app)
    return app


def _add_public_demo_guard(app: FastAPI) -> None:
    @app.middleware("http")
    async def read_only_public_demo(request, call_next):
        if not _blocks_public_demo_mutation(request.method, request.url.path):
            return await call_next(request)
        return JSONResponse(
            status_code=403,
            content={"detail": "Public demo mode is read-only"},
        )


def _blocks_public_demo_mutation(method: str, path: str) -> bool:
    if not settings.is_public_demo:
        return False
    if method.upper() not in MUTATING_METHODS:
        return False
    return not path.startswith("/api/v1/admin/")


def _include_routers(app: FastAPI) -> None:
    app.include_router(verticals.router, prefix="/api/v1/verticals", tags=["verticals"])
    app.include_router(tracking.router, prefix="/api/v1/tracking", tags=["tracking"])
    app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["metrics"])
    app.include_router(api_keys.router, prefix="/api/v1", tags=["api-keys"])
    app.include_router(
        consolidation.router,
        prefix="/api/v1/consolidation",
        tags=["consolidation"],
    )
    app.include_router(feedback.router, prefix="/api/v1", tags=["feedback"])
    app.include_router(knowledge.router, prefix="/api/v1", tags=["knowledge"])
    app.include_router(admin.router, prefix="/api/v1/admin", tags=["admin"])


def _include_health_routes(app: FastAPI) -> None:
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


app = create_app()
