import time

from sqlalchemy.exc import OperationalError


def _is_locked_message(message: str) -> bool:
    lowered = message.lower()
    return "database is locked" in lowered or "database is busy" in lowered


def _is_sqlite_locked_error(exc: OperationalError) -> bool:
    message = str(getattr(exc, "orig", exc))
    return _is_locked_message(message)


def _should_retry(exc: OperationalError, attempt: int, retries: int) -> bool:
    return _is_sqlite_locked_error(exc) and attempt < retries - 1


def _sleep_for_retry(delay: float, attempt: int) -> None:
    time.sleep(delay * (attempt + 1))


def commit_with_retry(session, retries: int = 3, delay: float = 0.1, attempt: int = 0) -> None:
    try:
        session.commit()
    except OperationalError as exc:
        session.rollback()
        if not _should_retry(exc, attempt, retries):
            raise
        _sleep_for_retry(delay, attempt)
        commit_with_retry(session, retries=retries, delay=delay, attempt=attempt + 1)


def flush_with_retry(session, retries: int = 3, delay: float = 0.1, attempt: int = 0) -> None:
    try:
        session.flush()
    except OperationalError as exc:
        session.rollback()
        if not _should_retry(exc, attempt, retries):
            raise
        _sleep_for_retry(delay, attempt)
        flush_with_retry(session, retries=retries, delay=delay, attempt=attempt + 1)
