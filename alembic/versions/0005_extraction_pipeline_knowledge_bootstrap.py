"""add extraction knowledge bootstrap fields

Revision ID: 0005
Revises: 0004
Create Date: 2026-03-12
"""

from __future__ import annotations

import re

import sqlalchemy as sa
from alembic import op


revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def _normalize_alias_key(text: str | None) -> str:
    cleaned = re.sub(r"\(.*?\)", "", (text or "").strip())
    cleaned = re.sub(r"（.*?）", "", cleaned)
    cleaned = re.sub(r"[\s\W_]+", "", cleaned, flags=re.UNICODE)
    return cleaned.casefold()


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    return name in inspector.get_table_names()


def _column_names(table_name: str) -> set[str]:
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_exists(name: str) -> bool:
    from sqlalchemy import inspect

    inspector = inspect(op.get_bind())
    for table in inspector.get_table_names():
        for index in inspector.get_indexes(table):
            if index["name"] == name:
                return True
    return False


def _bool_default(value: bool) -> sa.TextClause:
    if op.get_bind().dialect.name == "postgresql":
        return sa.text("true") if value else sa.text("false")
    return sa.text("1") if value else sa.text("0")


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if not _table_exists(table_name):
        return
    if column.name in _column_names(table_name):
        return
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(column)


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if not _table_exists(table_name):
        return
    if _index_exists(index_name):
        return
    op.create_index(index_name, table_name, columns, unique=False)


def _backfill_alias_keys(table_name: str, value_column: str) -> None:
    if not _table_exists(table_name):
        return
    bind = op.get_bind()
    rows = bind.execute(sa.text(f"SELECT id, {value_column} FROM {table_name}")).fetchall()
    for row_id, value in rows:
        bind.execute(
            sa.text(f"UPDATE {table_name} SET alias_key = :alias_key WHERE id = :row_id"),
            {"alias_key": _normalize_alias_key(value), "row_id": row_id},
        )


def upgrade() -> None:
    _add_column_if_missing(
        "knowledge_verticals",
        sa.Column("seeded_at", sa.DateTime(timezone=True), nullable=True),
    )
    _add_column_if_missing(
        "knowledge_verticals",
        sa.Column("seed_version", sa.String(length=50), nullable=True),
    )

    for table_name in (
        "knowledge_brands",
        "knowledge_brand_aliases",
        "knowledge_products",
        "knowledge_product_aliases",
        "knowledge_rejected_entities",
    ):
        _add_column_if_missing(
            table_name,
            sa.Column("alias_key", sa.String(length=255), nullable=True),
        )

    _create_index_if_missing("ix_knowledge_brands_alias_key", "knowledge_brands", ["alias_key"])
    _create_index_if_missing("ix_knowledge_brand_aliases_alias_key", "knowledge_brand_aliases", ["alias_key"])
    _create_index_if_missing("ix_knowledge_products_alias_key", "knowledge_products", ["alias_key"])
    _create_index_if_missing("ix_knowledge_product_aliases_alias_key", "knowledge_product_aliases", ["alias_key"])
    _create_index_if_missing(
        "ix_knowledge_rejected_entities_alias_key",
        "knowledge_rejected_entities",
        ["alias_key"],
    )

    _backfill_alias_keys("knowledge_brands", "canonical_name")
    _backfill_alias_keys("knowledge_brand_aliases", "alias")
    _backfill_alias_keys("knowledge_products", "canonical_name")
    _backfill_alias_keys("knowledge_product_aliases", "alias")
    _backfill_alias_keys("knowledge_rejected_entities", "name")

    if not _table_exists("knowledge_extraction_logs"):
        op.create_table(
            "knowledge_extraction_logs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("vertical_id", sa.Integer(), sa.ForeignKey("knowledge_verticals.id"), nullable=False),
            sa.Column("run_id", sa.Integer(), nullable=True),
            sa.Column("entity_name", sa.String(length=255), nullable=False),
            sa.Column("entity_type", sa.Enum("brand", "product", name="entitytype"), nullable=False),
            sa.Column("extraction_source", sa.String(length=50), nullable=False),
            sa.Column("resolved_to", sa.String(length=255), nullable=True),
            sa.Column("was_accepted", sa.Boolean(), nullable=False, server_default=_bool_default(True)),
            sa.Column("item_text", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )


def downgrade() -> None:
    if _table_exists("knowledge_extraction_logs"):
        op.drop_table("knowledge_extraction_logs")

    for index_name, table_name in (
        ("ix_knowledge_rejected_entities_alias_key", "knowledge_rejected_entities"),
        ("ix_knowledge_product_aliases_alias_key", "knowledge_product_aliases"),
        ("ix_knowledge_products_alias_key", "knowledge_products"),
        ("ix_knowledge_brand_aliases_alias_key", "knowledge_brand_aliases"),
        ("ix_knowledge_brands_alias_key", "knowledge_brands"),
    ):
        if _index_exists(index_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name, column_name in (
        ("knowledge_rejected_entities", "alias_key"),
        ("knowledge_product_aliases", "alias_key"),
        ("knowledge_products", "alias_key"),
        ("knowledge_brand_aliases", "alias_key"),
        ("knowledge_brands", "alias_key"),
        ("knowledge_verticals", "seed_version"),
        ("knowledge_verticals", "seeded_at"),
    ):
        if column_name in _column_names(table_name):
            with op.batch_alter_table(table_name) as batch_op:
                batch_op.drop_column(column_name)
