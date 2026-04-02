from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from config import settings
from models.sqlite_config import apply_sqlite_pragmas, is_sqlite_url, sqlite_connect_args


class KnowledgeBase(DeclarativeBase):
    pass


knowledge_engine = create_engine(
    settings.resolved_knowledge_database_url,
    connect_args=sqlite_connect_args(settings.resolved_knowledge_database_url),
    echo=settings.debug,
)
knowledge_read_engine = knowledge_engine
knowledge_write_engine = knowledge_engine

KnowledgeSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=knowledge_engine,
)
KnowledgeReadSessionLocal = KnowledgeSessionLocal
KnowledgeWriteSessionLocal = KnowledgeSessionLocal


def _apply_knowledge_sqlite_pragmas(dbapi_connection, _) -> None:
    apply_sqlite_pragmas(dbapi_connection)


if is_sqlite_url(settings.resolved_knowledge_database_url):
    event.listen(knowledge_engine, "connect", _apply_knowledge_sqlite_pragmas)


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
    KnowledgeBase.metadata.create_all(bind=knowledge_engine)
