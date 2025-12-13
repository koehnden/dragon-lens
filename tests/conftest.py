"""Test fixtures for API tests."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from api.routers import metrics, tracking, verticals
from models import Base, get_db


@pytest.fixture(scope="function")
def db_engine():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def test_app():
    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator:
        yield

    app = FastAPI(
        title="DragonLens Test",
        description="Track brand visibility in Chinese LLMs",
        version="0.1.0",
        lifespan=test_lifespan,
    )

    app.include_router(verticals.router, prefix="/api/v1/verticals", tags=["verticals"])
    app.include_router(tracking.router, prefix="/api/v1/tracking", tags=["tracking"])
    app.include_router(metrics.router, prefix="/api/v1/metrics", tags=["metrics"])

    @app.get("/")
    async def root():
        return {
            "name": "DragonLens",
            "version": "0.1.0",
            "status": "running",
        }

    @app.get("/health")
    async def health():
        return {"status": "healthy"}

    return app


@pytest.fixture(scope="function")
def client(db_session: Session, test_app: FastAPI):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    with TestClient(test_app) as test_client:
        yield test_client
    test_app.dependency_overrides.clear()
