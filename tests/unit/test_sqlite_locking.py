import sqlite3

import pytest
from sqlalchemy.exc import OperationalError

from models.db_retry import commit_with_retry, flush_with_retry
from models.sqlite_config import apply_sqlite_pragmas


class FakeSession:
    def __init__(self, commit_failures=0, flush_failures=0, error=None):
        self.commit_failures = commit_failures
        self.flush_failures = flush_failures
        self.error = error
        self.commit_calls = 0
        self.flush_calls = 0
        self.rollback_calls = 0

    def commit(self):
        self.commit_calls += 1
        if self.commit_calls <= self.commit_failures:
            raise self.error

    def flush(self):
        self.flush_calls += 1
        if self.flush_calls <= self.flush_failures:
            raise self.error

    def rollback(self):
        self.rollback_calls += 1


def test_apply_sqlite_pragmas_sets_values(tmp_path):
    db_path = tmp_path / "test.db"
    connection = sqlite3.connect(db_path)
    apply_sqlite_pragmas(connection)
    journal = connection.execute("PRAGMA journal_mode").fetchone()[0].lower()
    busy = connection.execute("PRAGMA busy_timeout").fetchone()[0]
    synchronous = connection.execute("PRAGMA synchronous").fetchone()[0]
    foreign_keys = connection.execute("PRAGMA foreign_keys").fetchone()[0]
    connection.close()
    assert journal == "wal"
    assert busy == 5000
    assert synchronous == 1
    assert foreign_keys == 1


def test_commit_with_retry_retries_on_locked():
    error = OperationalError("stmt", {}, sqlite3.OperationalError("database is locked"))
    session = FakeSession(commit_failures=2, error=error)
    commit_with_retry(session, retries=3, delay=0)
    assert session.commit_calls == 3
    assert session.rollback_calls == 2


def test_commit_with_retry_raises_on_other_error():
    error = OperationalError("stmt", {}, sqlite3.OperationalError("syntax error"))
    session = FakeSession(commit_failures=1, error=error)
    with pytest.raises(OperationalError):
        commit_with_retry(session, retries=2, delay=0)


def test_flush_with_retry_retries_on_locked():
    error = OperationalError("stmt", {}, sqlite3.OperationalError("database is locked"))
    session = FakeSession(flush_failures=2, error=error)
    flush_with_retry(session, retries=3, delay=0)
    assert session.flush_calls == 3
    assert session.rollback_calls == 2


def test_flush_with_retry_raises_on_other_error():
    error = OperationalError("stmt", {}, sqlite3.OperationalError("syntax error"))
    session = FakeSession(flush_failures=1, error=error)
    with pytest.raises(OperationalError):
        flush_with_retry(session, retries=2, delay=0)
