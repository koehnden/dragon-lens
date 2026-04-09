#!/usr/bin/env python3
"""DEPRECATED: Knowledge DB now uses PostgreSQL managed by Alembic.
Use `alembic upgrade head` instead. For data migration from SQLite,
use `scripts/migrate_knowledge_to_pg.py`.
"""

from sqlalchemy import text
from models.knowledge_database import knowledge_write_engine


def migrate():
    print("Migrating knowledge database schema...")

    with knowledge_write_engine.connect() as conn:
        # Add missing columns to knowledge_verticals
        try:
            conn.execute(text(
                "ALTER TABLE knowledge_verticals ADD COLUMN seeded_at DATETIME"
            ))
            print("✓ Added seeded_at column to knowledge_verticals")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("  seeded_at already exists")
            else:
                print(f"  Error adding seeded_at: {e}")

        try:
            conn.execute(text(
                "ALTER TABLE knowledge_verticals ADD COLUMN seed_version VARCHAR(50)"
            ))
            print("✓ Added seed_version column to knowledge_verticals")
        except Exception as e:
            if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                print("  seed_version already exists")
            else:
                print(f"  Error adding seed_version: {e}")

        # Add alias_key columns to various tables
        tables_needing_alias_key = [
            ("knowledge_brands", "canonical_name"),
            ("knowledge_brand_aliases", "alias"),
            ("knowledge_products", "canonical_name"),
            ("knowledge_product_aliases", "alias"),
            ("knowledge_rejected_entities", "name"),
            ("knowledge_vertical_aliases", "alias"),
        ]

        for table_name, _ in tables_needing_alias_key:
            try:
                conn.execute(text(
                    f"ALTER TABLE {table_name} ADD COLUMN alias_key VARCHAR(255) DEFAULT ''"
                ))
                print(f"✓ Added alias_key column to {table_name}")
            except Exception as e:
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"  alias_key already exists in {table_name}")
                else:
                    print(f"  Error adding alias_key to {table_name}: {e}")

        # Create indexes
        indexes = [
            ("knowledge_brands", "alias_key"),
            ("knowledge_brand_aliases", "alias_key"),
            ("knowledge_products", "alias_key"),
            ("knowledge_product_aliases", "alias_key"),
            ("knowledge_rejected_entities", "alias_key"),
            ("knowledge_vertical_aliases", "alias_key"),
        ]

        for table_name, column_name in indexes:
            try:
                conn.execute(text(
                    f"CREATE INDEX IF NOT EXISTS ix_{table_name}_{column_name} ON {table_name}({column_name})"
                ))
                print(f"✓ Created index on {table_name}.{column_name}")
            except Exception as e:
                print(f"  Error creating index on {table_name}.{column_name}: {e}")

        conn.commit()

    print("\n✅ Migration completed!")


if __name__ == "__main__":
    migrate()
