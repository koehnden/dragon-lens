from contextlib import contextmanager

from sqlalchemy.orm import Session

from models.knowledge_database import (
    KnowledgeReadSessionLocal,
    KnowledgeWriteSessionLocal,
    init_knowledge_db,
)

_initialized = False


def _ensure_initialized() -> None:
    global _initialized
    if not _initialized:
        init_knowledge_db()
        _initialized = True


def _session(existing: Session | None, write: bool) -> tuple[Session, bool]:
    if existing:
        return existing, False
    _ensure_initialized()
    session_factory = KnowledgeWriteSessionLocal if write else KnowledgeReadSessionLocal
    return session_factory(), True


def _commit(db: Session, write: bool, owned: bool) -> None:
    if write and owned:
        db.commit()


def _rollback(db: Session, write: bool, owned: bool) -> None:
    if write and owned:
        db.rollback()


@contextmanager
def knowledge_session(existing: Session | None = None, write: bool = False):
    db, owned = _session(existing, write)
    try:
        yield db
        _commit(db, write, owned)
    except Exception:
        _rollback(db, write, owned)
        raise
    finally:
        if owned:
            db.close()
