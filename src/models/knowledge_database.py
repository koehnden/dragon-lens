"""
Knowledge database configuration.

Uses the same PostgreSQL database as the main application for simplicity.
This eliminates TursoDB stream issues and simplifies deployment.
"""

from typing import Generator

from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from models.database import engine


class KnowledgeBase(DeclarativeBase):
    """Declarative base for knowledge tables."""
    pass


# Use the same PostgreSQL engine as the main database
knowledge_engine = engine
knowledge_read_engine = engine
knowledge_write_engine = engine

# Session factories bound to PostgreSQL
KnowledgeSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
KnowledgeReadSessionLocal = KnowledgeSessionLocal
KnowledgeWriteSessionLocal = KnowledgeSessionLocal


def get_knowledge_db() -> Generator[Session, None, None]:
    """Get a knowledge database session (read)."""
    db = KnowledgeSessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_knowledge_db_write() -> Generator[Session, None, None]:
    """Get a knowledge database session (write)."""
    db = KnowledgeSessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_knowledge_db() -> None:
    """Initialize knowledge tables in PostgreSQL."""
    KnowledgeBase.metadata.create_all(bind=engine)
