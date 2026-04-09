"""migrate knowledge tables to postgresql

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-05
"""

from __future__ import annotations

from alembic import op


revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

KNOWLEDGE_TABLES = [
    "knowledge_extraction_logs",
    "knowledge_feedback_events",
    "knowledge_translation_overrides",
    "knowledge_product_brand_mappings",
    "knowledge_product_aliases",
    "knowledge_products",
    "knowledge_rejected_entities",
    "knowledge_brand_aliases",
    "knowledge_brands",
    "knowledge_vertical_aliases",
    "knowledge_verticals",
]


ENUM_COLUMNS = [
    ("knowledge_rejected_entities", "entity_type"),
    ("knowledge_translation_overrides", "entity_type"),
    ("knowledge_extraction_logs", "entity_type"),
    ("knowledge_feedback_events", "status"),
]


def upgrade() -> None:
    import models.knowledge_domain  # noqa: F401

    from models.knowledge_database import KnowledgeBase

    KnowledgeBase.metadata.create_all(bind=op.get_bind())

    # create_all reuses existing native PG enums even when models specify
    # native_enum=False. Convert these columns to VARCHAR so SQLAlchemy
    # sends string values correctly.
    for table, column in ENUM_COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE VARCHAR(255) USING {column}::text"
        )


def downgrade() -> None:
    for table_name in KNOWLEDGE_TABLES:
        op.drop_table(table_name)
