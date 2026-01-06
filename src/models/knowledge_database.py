from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from models.sqlite_config import apply_sqlite_pragmas, is_sqlite_url, sqlite_connect_args
from src.config import settings


class KnowledgeBase(DeclarativeBase):
    pass


def _sqlite_path(url: str) -> str | None:
    if not url.startswith("sqlite:///"):
        return None
    return url.replace("sqlite:///", "", 1)


def _ensure_dir(url: str) -> None:
    path = _sqlite_path(url)
    if not path or path == ":memory:":
        return
    Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)


def _is_memory_url(url: str) -> bool:
    return url == "sqlite:///:memory:"


def _engine_args(url: str) -> dict:
    args = {
        "connect_args": sqlite_connect_args(url),
        "echo": settings.debug,
    }
    if _is_memory_url(url):
        args["poolclass"] = StaticPool
    return args


_ensure_dir(settings.knowledge_database_url)

knowledge_engine = create_engine(
    settings.knowledge_database_url,
    **_engine_args(settings.knowledge_database_url),
)

KnowledgeSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=knowledge_engine)


def _apply_sqlite_pragmas(dbapi_connection, _):
    apply_sqlite_pragmas(dbapi_connection)


if is_sqlite_url(settings.knowledge_database_url):
    event.listen(knowledge_engine, "connect", _apply_sqlite_pragmas)


def get_knowledge_db() -> Generator[Session, None, None]:
    db = KnowledgeSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_knowledge_db() -> None:
    KnowledgeBase.metadata.create_all(bind=knowledge_engine)
