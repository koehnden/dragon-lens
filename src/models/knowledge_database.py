from pathlib import Path
from typing import Generator
from urllib.parse import urlencode

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from models.sqlite_config import (
    apply_sqlite_pragmas,
    is_sqlite_url,
    sqlite_connect_args,
)
from config import settings


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


def _engine_args(url: str, auth_token: str | None = None) -> dict:
    args = {
        "connect_args": sqlite_connect_args(url),
        "echo": settings.debug,
    }
    if auth_token:
        args["connect_args"]["auth_token"] = auth_token
        args["pool_pre_ping"] = True
    if _is_memory_url(url):
        args["poolclass"] = StaticPool
    return args


def _turso_enabled() -> bool:
    return bool(
        settings.turso_database_url
        and (settings.turso_read_only_auth_token or settings.turso_auth_token)
    )


def _turso_host() -> str:
    base = (settings.turso_database_url or "").strip()
    for prefix in ("libsql://", "https://", "http://"):
        if base.startswith(prefix):
            base = base[len(prefix) :]
    return base.rstrip("/")


def _libsql_url() -> str:
    host = _turso_host()
    if not host:
        return ""
    query = {"secure": "true"}
    return f"sqlite+libsql://{host}/?{urlencode(query)}"


def _turso_read_token() -> str | None:
    return settings.turso_read_only_auth_token or settings.turso_auth_token


def _turso_write_token() -> str | None:
    return settings.turso_auth_token or settings.turso_read_only_auth_token


def _knowledge_read_url() -> str:
    if not _turso_enabled():
        return settings.knowledge_database_url
    return _libsql_url()


def _knowledge_write_url() -> str:
    if not _turso_enabled():
        return settings.knowledge_database_url
    if not settings.turso_auth_token:
        return _knowledge_read_url()
    return _libsql_url()


knowledge_read_url = _knowledge_read_url()
knowledge_write_url = _knowledge_write_url()

if is_sqlite_url(knowledge_read_url):
    _ensure_dir(knowledge_read_url)

knowledge_read_engine = create_engine(
    knowledge_read_url,
    **_engine_args(
        knowledge_read_url, _turso_read_token() if _turso_enabled() else None
    ),
)
knowledge_write_engine = knowledge_read_engine
if not (
    is_sqlite_url(knowledge_read_url) and knowledge_write_url == knowledge_read_url
):
    knowledge_write_engine = create_engine(
        knowledge_write_url,
        **_engine_args(
            knowledge_write_url, _turso_write_token() if _turso_enabled() else None
        ),
    )

KnowledgeReadSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=knowledge_read_engine
)
KnowledgeWriteSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=knowledge_write_engine
)


def _apply_sqlite_pragmas(dbapi_connection, _):
    apply_sqlite_pragmas(dbapi_connection)


if is_sqlite_url(knowledge_read_url):
    event.listen(knowledge_read_engine, "connect", _apply_sqlite_pragmas)
if knowledge_write_engine is not knowledge_read_engine and is_sqlite_url(
    knowledge_write_url
):
    event.listen(knowledge_write_engine, "connect", _apply_sqlite_pragmas)

knowledge_engine = knowledge_read_engine
KnowledgeSessionLocal = KnowledgeReadSessionLocal


def get_knowledge_db() -> Generator[Session, None, None]:
    db = KnowledgeReadSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_knowledge_db_write() -> Generator[Session, None, None]:
    db = KnowledgeWriteSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_knowledge_db() -> None:
    if _turso_enabled() and not settings.turso_auth_token:
        return
    KnowledgeBase.metadata.create_all(bind=knowledge_write_engine)
