"""Script to selectively clear data from the database."""

import argparse
import logging
import sys
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def clear_data(clear_prompts_results: bool = False) -> None:
    engine = create_engine(settings.database_url)
    Session = sessionmaker(bind=engine)
    session = Session()
    
    try:
        session.execute(text("BEGIN"))
        
        if clear_prompts_results:
            logger.info("Clearing ALL data including prompt results...")
            
            tables = [
                "daily_metrics",
                "run_metrics", 
                "brand_mentions",
                "product_mentions",
                "llm_answers",
                "runs",
                "products",
                "brands", 
                "prompts",
                "verticals",
                "api_keys"
            ]
            
            for table in tables:
                logger.info(f"  Deleting from {table}...")
                session.execute(text(f"DELETE FROM {table}"))
                count = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                logger.info(f"    {table}: {count} rows remaining")
                
        else:
            logger.info("Clearing extracted data but keeping prompt results...")
            
            tables_to_clear = [
                "daily_metrics",
                "run_metrics",
                "brand_mentions", 
                "product_mentions"
            ]
            
            for table in tables_to_clear:
                logger.info(f"  Deleting from {table}...")
                session.execute(text(f"DELETE FROM {table}"))
                count = session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                logger.info(f"    {table}: {count} rows remaining")
            
            logger.info("  Resetting run statuses to PENDING...")
            session.execute(text("""
                UPDATE runs 
                SET status = 'pending', 
                    completed_at = NULL,
                    error_message = NULL
                WHERE status IN ('completed', 'failed')
            """))
            updated = session.execute(text("SELECT changes()")).scalar()
            logger.info(f"    Updated {updated} runs")
        
        session.execute(text("COMMIT"))
        logger.info("✓ Data cleared successfully")
        
    except Exception as e:
        session.execute(text("ROLLBACK"))
        logger.error(f"✗ Error clearing data: {e}")
        raise
    finally:
        session.close()


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
