"""add comparison prompt tables

Revision ID: 0003
Revises: 0002
Create Date: 2026-01-09
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _bind_dialect() -> str:
    return op.get_bind().dialect.name


def _existing_enum(name: str, values: list[str]):
    if _bind_dialect() == "postgresql":
        from sqlalchemy.dialects import postgresql

        return postgresql.ENUM(*values, name=name, create_type=False)
    return sa.Enum(*values, name=name)


def _new_enum(name: str, values: list[str]):
    if _bind_dialect() == "postgresql":
        from sqlalchemy.dialects import postgresql

        return postgresql.ENUM(*values, name=name, create_type=False)
    return sa.Enum(*values, name=name)

def _bool_default(value: bool) -> sa.TextClause:
    if _bind_dialect() == "postgresql":
        return sa.text("true") if value else sa.text("false")
    return sa.text("1") if value else sa.text("0")


def _table_exists(name: str) -> bool:
    from sqlalchemy import inspect
    inspector = inspect(op.get_bind())
    return name in inspector.get_table_names()


def _index_exists(name: str) -> bool:
    from sqlalchemy import inspect
    inspector = inspect(op.get_bind())
    for table in inspector.get_table_names():
        for idx in inspector.get_indexes(table):
            if idx["name"] == name:
                return True
    return False


def upgrade() -> None:
    if not _table_exists("run_comparison_configs"):
        op.create_table(
            "run_comparison_configs",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False, unique=True),
            sa.Column("vertical_id", sa.Integer(), sa.ForeignKey("verticals.id"), nullable=False),
            sa.Column("primary_brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=_bool_default(False)),
            sa.Column("competitor_brands", sa.JSON(), nullable=False),
            sa.Column("target_count", sa.Integer(), nullable=False, server_default=sa.text("20")),
            sa.Column("min_prompts_per_competitor", sa.Integer(), nullable=False, server_default=sa.text("2")),
            sa.Column("autogenerate_missing", sa.Boolean(), nullable=False, server_default=_bool_default(True)),
            sa.Column(
                "status",
                _new_enum("comparisonrunstatus", ["PENDING", "IN_PROGRESS", "COMPLETED", "FAILED", "SKIPPED"]),
                nullable=False,
                server_default=sa.text("'PENDING'"),
            ),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if not _index_exists("ix_run_comparison_configs_run_id"):
        op.create_index("ix_run_comparison_configs_run_id", "run_comparison_configs", ["run_id"], unique=True)

    if not _table_exists("comparison_prompts"):
        op.create_table(
            "comparison_prompts",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
            sa.Column("vertical_id", sa.Integer(), sa.ForeignKey("verticals.id"), nullable=False),
            sa.Column(
                "prompt_type",
                _new_enum("comparisonprompttype", ["BRAND_VS_BRAND", "PRODUCT_VS_PRODUCT"]),
                nullable=False,
            ),
            sa.Column(
                "source",
                _new_enum("comparisonpromptsource", ["USER", "GENERATED"]),
                nullable=False,
            ),
            sa.Column("text_en", sa.Text(), nullable=True),
            sa.Column("text_zh", sa.Text(), nullable=True),
            sa.Column(
                "language_original",
                _existing_enum("promptlanguage", ["EN", "ZH"]),
                nullable=False,
                server_default=sa.text("'ZH'"),
            ),
            sa.Column("primary_brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=True),
            sa.Column("competitor_brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=True),
            sa.Column("primary_product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
            sa.Column("competitor_product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
            sa.Column("aspects", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if not _index_exists("ix_comparison_prompts_run_id"):
        op.create_index("ix_comparison_prompts_run_id", "comparison_prompts", ["run_id"], unique=False)

    if not _table_exists("comparison_answers"):
        op.create_table(
            "comparison_answers",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
            sa.Column("comparison_prompt_id", sa.Integer(), sa.ForeignKey("comparison_prompts.id"), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("model_name", sa.String(length=255), nullable=False),
            sa.Column("route", _existing_enum("llmroute", ["LOCAL", "VENDOR", "OPENROUTER"]), nullable=True),
            sa.Column("raw_answer_zh", sa.Text(), nullable=False),
            sa.Column("raw_answer_en", sa.Text(), nullable=True),
            sa.Column("tokens_in", sa.Integer(), nullable=True),
            sa.Column("tokens_out", sa.Integer(), nullable=True),
            sa.Column("latency", sa.Float(), nullable=True),
            sa.Column("cost_estimate", sa.Float(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("run_id", "comparison_prompt_id", name="uq_comparison_answers_run_prompt"),
        )
    if not _index_exists("ix_comparison_answers_run_id"):
        op.create_index("ix_comparison_answers_run_id", "comparison_answers", ["run_id"], unique=False)

    if not _table_exists("comparison_sentiment_observations"):
        op.create_table(
            "comparison_sentiment_observations",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
            sa.Column("comparison_answer_id", sa.Integer(), sa.ForeignKey("comparison_answers.id"), nullable=False),
            sa.Column("entity_type", _existing_enum("entitytype", ["BRAND", "PRODUCT"]), nullable=False),
            sa.Column("entity_id", sa.Integer(), nullable=False),
            sa.Column(
                "entity_role",
                _new_enum("comparisonentityrole", ["PRIMARY", "COMPETITOR"]),
                nullable=False,
            ),
            sa.Column("aspect", sa.String(length=255), nullable=True),
            sa.Column("sentiment", _existing_enum("sentiment", ["POSITIVE", "NEUTRAL", "NEGATIVE"]), nullable=False),
            sa.Column("snippet_zh", sa.Text(), nullable=False),
            sa.Column("snippet_en", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if not _index_exists("ix_comparison_sentiment_observations_run_entity"):
        op.create_index(
            "ix_comparison_sentiment_observations_run_entity",
            "comparison_sentiment_observations",
            ["run_id", "entity_type", "entity_id"],
            unique=False,
        )

    if not _table_exists("comparison_run_events"):
        op.create_table(
            "comparison_run_events",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
            sa.Column("level", sa.String(length=20), nullable=False),
            sa.Column("code", sa.String(length=50), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        )
    if not _index_exists("ix_comparison_run_events_run_id"):
        op.create_index("ix_comparison_run_events_run_id", "comparison_run_events", ["run_id"], unique=False)

    if not _table_exists("run_product_metrics"):
        op.create_table(
            "run_product_metrics",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("mention_rate", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("share_of_voice", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("top_spot_share", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("sentiment_index", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("dragon_lens_visibility", sa.Float(), nullable=False, server_default=sa.text("0.0")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("run_id", "product_id", name="uq_run_product_metrics_run_product"),
        )
    if not _index_exists("ix_run_product_metrics_run_id"):
        op.create_index("ix_run_product_metrics_run_id", "run_product_metrics", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_run_product_metrics_run_id", table_name="run_product_metrics")
    op.drop_constraint("uq_run_product_metrics_run_product", "run_product_metrics", type_="unique")
    op.drop_table("run_product_metrics")

    op.drop_index("ix_comparison_run_events_run_id", table_name="comparison_run_events")
    op.drop_table("comparison_run_events")

    op.drop_index(
        "ix_comparison_sentiment_observations_run_entity",
        table_name="comparison_sentiment_observations",
    )
    op.drop_table("comparison_sentiment_observations")

    op.drop_index("ix_comparison_answers_run_id", table_name="comparison_answers")
    op.drop_constraint("uq_comparison_answers_run_prompt", "comparison_answers", type_="unique")
    op.drop_table("comparison_answers")

    op.drop_index("ix_comparison_prompts_run_id", table_name="comparison_prompts")
    op.drop_table("comparison_prompts")

    op.drop_index("ix_run_comparison_configs_run_id", table_name="run_comparison_configs")
    op.drop_table("run_comparison_configs")
