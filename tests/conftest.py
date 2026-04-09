"""Test fixtures for API tests."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import sys
from pathlib import Path
import os


def ensure_src_on_path() -> None:
    root = Path(__file__).resolve().parent.parent
    src_path = root / "src"
    src_value = str(src_path)
    if src_value in sys.path:
        sys.path.remove(src_value)
    sys.path.insert(0, src_value)


ensure_src_on_path()


def _set_env_default(name: str, value: str) -> None:
    if not os.environ.get(name):
        os.environ[name] = value


_set_env_default("CELERY_BROKER_URL", "memory://")
_set_env_default("CELERY_RESULT_BACKEND", "cache+memory://")
_set_env_default("DATABASE_URL", "sqlite:///:memory:")
_set_env_default("ENABLE_QWEN_FILTERING", "false")
_set_env_default("RUN_TASKS_INLINE", "true")
_set_env_default("KNOWLEDGE_DATABASE_URL", "sqlite:///:memory:")
os.environ["FEEDBACK_SANITY_CHECKS_ENABLED"] = "false"
os.environ["FEEDBACK_TRIGGER_RERUN_ENABLED"] = "false"
os.environ["VERTICAL_AUTO_MATCH_ENABLED"] = "false"
_set_env_default("ENCRYPTION_SECRET_KEY", "test-secret-key")


def _routers():
    try:
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
    except ImportError:
        from src.api.routers import (
            admin,
            api_keys,
            consolidation,
            feedback,
            knowledge,
            metrics,
            tracking,
            verticals,
        )
    return (
        admin,
        api_keys,
        consolidation,
        feedback,
        knowledge,
        metrics,
        tracking,
        verticals,
    )


def _models():
    from models import Base, get_db

    return Base, get_db


def _knowledge_models():
    import models.knowledge_domain  # noqa: F401

    from models.knowledge_database import (
        KnowledgeBase,
        get_knowledge_db,
        get_knowledge_db_write,
        knowledge_engine,
    )

    return KnowledgeBase, get_knowledge_db, get_knowledge_db_write, knowledge_engine


@pytest.fixture(scope="function")
def db_engine():
    Base, _ = _models()
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
def knowledge_db_engine():
    KnowledgeBase, _, _, _ = _knowledge_models()
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    KnowledgeBase.metadata.create_all(bind=engine)
    yield engine
    KnowledgeBase.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def knowledge_db_session(knowledge_db_engine):
    connection = knowledge_db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


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
def db(db_session: Session) -> Session:
    return db_session


@pytest.fixture(scope="function")
def test_app():
    try:
        from api.app import create_app
    except ImportError:
        from src.api.app import create_app

    @asynccontextmanager
    async def test_lifespan(app: FastAPI) -> AsyncGenerator:
        yield

    return create_app(app_lifespan=test_lifespan)


@pytest.fixture(scope="function")
def client(db_session: Session, knowledge_db_session: Session, test_app: FastAPI):
    _, get_db = _models()
    _, get_knowledge_db, get_knowledge_db_write, _ = _knowledge_models()

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    def override_get_knowledge_db():
        try:
            yield knowledge_db_session
        finally:
            pass

    def override_get_knowledge_db_write():
        try:
            yield knowledge_db_session
        finally:
            pass

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_knowledge_db] = override_get_knowledge_db
    test_app.dependency_overrides[get_knowledge_db_write] = (
        override_get_knowledge_db_write
    )
    with TestClient(test_app) as test_client:
        yield test_client
    test_app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def reset_global_knowledge_db():
    KnowledgeBase, _, _, knowledge_engine = _knowledge_models()
    KnowledgeBase.metadata.create_all(bind=knowledge_engine)
    with knowledge_engine.begin() as connection:
        for table in reversed(KnowledgeBase.metadata.sorted_tables):
            connection.execute(table.delete())
    yield
