from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.util.exc import CommandError


def upgrade_db(revision: str = "head") -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    try:
        command.upgrade(config, revision)
    except CommandError as exc:
        message = (
            "Database migration failed. "
            "This usually means the DB is stamped with a revision that is missing in this repo. "
            f"Original error: {exc}"
        )
        raise RuntimeError(message) from exc
