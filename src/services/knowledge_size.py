from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from models.sqlite_config import is_sqlite_url


def _pragma_int(db: Session, name: str) -> int | None:
    try:
        value = db.execute(text(f"PRAGMA {name}")).scalar()
    except Exception:
        return None
    return int(value) if value is not None else None


def _event_payload_bytes(db: Session) -> int | None:
    try:
        value = db.execute(text("SELECT SUM(LENGTH(payload)) FROM knowledge_feedback_events")).scalar()
    except Exception:
        return None
    return int(value) if value is not None else 0


def _pg_knowledge_size(db: Session) -> int | None:
    try:
        result = db.execute(text(
            "SELECT SUM(pg_total_relation_size(quote_ident(tablename))) "
            "FROM pg_tables WHERE schemaname = 'public' "
            "AND tablename LIKE 'knowledge\\_%'"
        )).scalar()
        return int(result) if result is not None else 0
    except Exception:
        return _event_payload_bytes(db)


def knowledge_db_size_bytes(db: Session) -> int | None:
    if is_sqlite_url(settings.resolved_knowledge_database_url):
        page_size = _pragma_int(db, "page_size")
        page_count = _pragma_int(db, "page_count")
        if page_size is not None and page_count is not None:
            return page_size * page_count
        return _event_payload_bytes(db)
    return _pg_knowledge_size(db)
