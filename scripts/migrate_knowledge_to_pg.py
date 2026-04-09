"""One-time migration of knowledge data from SQLite to PostgreSQL.

Usage:
    poetry run python scripts/migrate_knowledge_to_pg.py [--sqlite-path data/knowledge.db]
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from config import settings  # noqa: E402
from models.knowledge_database import KnowledgeBase  # noqa: E402

import models.knowledge_domain as kd  # noqa: E402, F401

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

TABLES_IN_FK_ORDER = [
    kd.KnowledgeVertical,
    kd.KnowledgeVerticalAlias,
    kd.KnowledgeBrand,
    kd.KnowledgeBrandAlias,
    kd.KnowledgeProduct,
    kd.KnowledgeProductAlias,
    kd.KnowledgeRejectedEntity,
    kd.KnowledgeProductBrandMapping,
    kd.KnowledgeTranslationOverride,
    kd.KnowledgeFeedbackEvent,
    kd.KnowledgeExtractionLog,
]


def _copy_table(
    sqlite_session: Session, pg_session: Session, model: type
) -> int:
    table_name = model.__tablename__
    rows = sqlite_session.query(model).all()
    if not rows:
        logger.info("  %s: 0 rows (empty)", table_name)
        return 0

    columns = [c.key for c in model.__table__.columns]
    inserted = 0
    for row in rows:
        row_dict = {col: getattr(row, col) for col in columns}
        try:
            pg_session.execute(model.__table__.insert(), row_dict)
            inserted += 1
        except Exception:
            pg_session.rollback()
            continue

    pg_session.commit()
    logger.info("  %s: %d/%d rows copied", table_name, inserted, len(rows))
    return inserted


def _reset_sequences(pg_session: Session) -> None:
    for model in TABLES_IN_FK_ORDER:
        table_name = model.__tablename__
        seq_name = f"{table_name}_id_seq"
        try:
            max_id = pg_session.execute(
                text(f"SELECT MAX(id) FROM {table_name}")
            ).scalar()
            if max_id is not None:
                pg_session.execute(
                    text(f"SELECT setval('{seq_name}', :val)"),
                    {"val": max_id},
                )
                logger.info("  %s sequence reset to %d", table_name, max_id)
        except Exception as exc:
            logger.warning("  %s sequence reset failed: %s", table_name, exc)
            pg_session.rollback()
    pg_session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate knowledge DB from SQLite to PostgreSQL")
    parser.add_argument(
        "--sqlite-path",
        default="data/knowledge.db",
        help="Path to SQLite knowledge database (default: data/knowledge.db)",
    )
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path)
    if not sqlite_path.exists():
        logger.error("SQLite database not found: %s", sqlite_path)
        sys.exit(1)

    pg_url = settings.database_url
    sqlite_url = f"sqlite:///{sqlite_path}"

    logger.info("Source: %s", sqlite_url)
    logger.info("Target: %s", pg_url)

    sqlite_engine = create_engine(sqlite_url)
    pg_engine = create_engine(pg_url)

    KnowledgeBase.metadata.create_all(bind=pg_engine)
    logger.info("Target tables ensured.")

    sqlite_session = Session(bind=sqlite_engine)
    pg_session = Session(bind=pg_engine)

    try:
        logger.info("Copying tables...")
        total = 0
        for model in TABLES_IN_FK_ORDER:
            total += _copy_table(sqlite_session, pg_session, model)

        logger.info("Resetting sequences...")
        _reset_sequences(pg_session)

        logger.info("Done. %d total rows migrated.", total)
    finally:
        sqlite_session.close()
        pg_session.close()
        sqlite_engine.dispose()
        pg_engine.dispose()


if __name__ == "__main__":
    main()
