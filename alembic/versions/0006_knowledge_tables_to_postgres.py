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


def upgrade() -> None:
    import models.knowledge_domain  # noqa: F401

    from models.knowledge_database import KnowledgeBase

    KnowledgeBase.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    for table_name in KNOWLEDGE_TABLES:
        op.drop_table(table_name)
