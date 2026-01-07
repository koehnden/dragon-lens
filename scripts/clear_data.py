"""Script to selectively clear data from the database."""

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _dialect(engine) -> str:
    return engine.dialect.name


def _is_postgres(engine) -> bool:
    return _dialect(engine) == "postgresql"


def _quote_table(name: str) -> str:
    return f'"{name}"'


def _table_names(engine) -> list[str]:
    return list(inspect(engine).get_table_names())


def _tables_in_order(names: list[str], candidates: list[str]) -> list[str]:
    existing = set(names)
    return [t for t in candidates if t in existing]


def _clear_all_tables_sqlite(session, engine) -> None:
    tables = _tables_in_order(
        _table_names(engine),
        [
            "daily_metrics",
            "run_metrics",
            "brand_mentions",
            "product_mentions",
            "extraction_debug",
            "consolidation_debug",
            "product_brand_mappings",
            "llm_answers",
            "runs",
            "products",
            "brands",
            "prompts",
            "verticals",
            "api_keys",
        ],
    )
    for table in tables:
        logger.info(f"  Deleting from {table}...")
        session.execute(text(f"DELETE FROM {table}"))
        count = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        logger.info(f"    {table}: {count} rows remaining")


def _clear_all_tables_postgres(session, engine) -> None:
    tables = [t for t in _table_names(engine) if t != "alembic_version"]
    if not tables:
        return
    quoted = ", ".join(_quote_table(t) for t in tables)
    session.execute(text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE"))


def _clear_extracted_tables(session, engine) -> None:
    tables = _tables_in_order(
        _table_names(engine),
        [
            "daily_metrics",
            "run_metrics",
            "brand_mentions",
            "product_mentions",
            "extraction_debug",
            "consolidation_debug",
        ],
    )
    for table in tables:
        logger.info(f"  Deleting from {table}...")
        session.execute(text(f"DELETE FROM {table}"))
        count = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
        logger.info(f"    {table}: {count} rows remaining")


def clear_data(clear_prompts_results: bool = False) -> None:
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        status_mode = _detect_run_status_storage(session)
        
        if clear_prompts_results:
            logger.info("Clearing ALL data including prompt results...")
            if _is_postgres(engine):
                _clear_all_tables_postgres(session, engine)
            else:
                _clear_all_tables_sqlite(session, engine)
                
        else:
            logger.info("Clearing extracted data but keeping prompt results...")
            _clear_extracted_tables(session, engine)
            
            logger.info("  Resetting run statuses to PENDING...")
            result = session.execute(text(_reset_runs_sql(status_mode)))
            logger.info(f"    Updated {result.rowcount or 0} runs")

        session.commit()
        logger.info("✓ Data cleared successfully")
        
    except Exception as e:
        session.rollback()
        logger.error(f"✗ Error clearing data: {e}")
        raise
    finally:
        session.close()


def _detect_run_status_storage(session) -> str:
    sample = session.execute(text("SELECT status FROM runs LIMIT 1")).scalar()
    if not sample:
        return "name"
    return "value" if str(sample).islower() else "name"


def _reset_runs_sql(status_mode: str) -> str:
    if status_mode == "value":
        return (
            "UPDATE runs SET status = 'pending', completed_at = NULL, error_message = NULL "
            "WHERE lower(status) IN ('completed', 'failed', 'in_progress')"
        )
    return (
        "UPDATE runs SET status = 'PENDING', completed_at = NULL, error_message = NULL "
        "WHERE upper(status) IN ('COMPLETED', 'FAILED', 'IN_PROGRESS')"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Clear data from DragonLens database")
    parser.add_argument(
        "--clear-prompts-results",
        action="store_true",
        default=False,
        help="Clear all data including prompt results (LLM answers). Default: False (keep prompt results)"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        default=False,
        help="Skip confirmation prompt (useful for scripts)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("DragonLens Data Clear Utility")
    print("=" * 60)
    
    if args.clear_prompts_results:
        print("Mode: CLEAR ALL DATA (including prompt results)")
        print("This will delete:")
        print("  - All verticals, brands, products, prompts")
        print("  - All LLM answers (prompt responses)")
        print("  - All extracted mentions and metrics")
        print("  - All API keys")
    else:
        print("Mode: CLEAR EXTRACTED DATA ONLY (keep prompt results)")
        print("This will delete:")
        print("  - All brand and product mentions")
        print("  - All daily and run metrics")
        print("  - Reset run statuses to PENDING")
        print("This will keep:")
        print("  - Verticals, brands, products, prompts")
        print("  - LLM answers (prompt responses - expensive to regenerate)")
        print("  - API keys")
    
    if not args.yes:
        print("\n" + "=" * 60)
        try:
            confirmation = input("Are you sure you want to proceed? (yes/no): ")
        except EOFError:
            print("\n⚠  No terminal input available. Use --yes flag to skip confirmation.")
            print("Operation cancelled.")
            sys.exit(1)
        
        if confirmation.lower() != "yes":
            print("Operation cancelled.")
            sys.exit(0)
    
    try:
        clear_data(args.clear_prompts_results)
        print("\n✅ Operation completed successfully!")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
