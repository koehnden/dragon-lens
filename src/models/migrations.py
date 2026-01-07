from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade_db(revision: str = "head") -> None:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(config, revision)
