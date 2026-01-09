from sqlalchemy import text
from sqlalchemy.orm import Session


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


def knowledge_db_size_bytes(db: Session) -> int | None:
    page_size = _pragma_int(db, "page_size")
    page_count = _pragma_int(db, "page_count")
    if page_size is not None and page_count is not None:
        return page_size * page_count
    return _event_payload_bytes(db)

