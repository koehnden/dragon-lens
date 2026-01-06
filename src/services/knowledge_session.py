from contextlib import contextmanager

from sqlalchemy.orm import Session

from models.knowledge_database import KnowledgeSessionLocal, init_knowledge_db

_initialized = False


def _ensure_initialized() -> None:
    global _initialized
    if not _initialized:
        init_knowledge_db()
        _initialized = True


@contextmanager
def knowledge_session(existing: Session | None = None):
    if existing:
        yield existing
        return
    _ensure_initialized()
    db = KnowledgeSessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
