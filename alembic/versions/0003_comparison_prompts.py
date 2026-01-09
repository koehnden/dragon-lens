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


def upgrade() -> None:
    op.create_table(
        "run_comparison_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False, unique=True),
        sa.Column("vertical_id", sa.Integer(), sa.ForeignKey("verticals.id"), nullable=False),
        sa.Column("primary_brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("competitor_brands", sa.JSON(), nullable=False),
        sa.Column("target_count", sa.Integer(), nullable=False, server_default=sa.text("20")),
        sa.Column("min_prompts_per_competitor", sa.Integer(), nullable=False, server_default=sa.text("2")),
        sa.Column("autogenerate_missing", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "status",
            sa.Enum("pending", "in_progress", "completed", "failed", "skipped", name="comparisonrunstatus"),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_run_comparison_configs_run_id", "run_comparison_configs", ["run_id"], unique=True)

    op.create_table(
        "comparison_prompts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("vertical_id", sa.Integer(), sa.ForeignKey("verticals.id"), nullable=False),
        sa.Column(
            "prompt_type",
            sa.Enum("brand_vs_brand", "product_vs_product", name="comparisonprompttype"),
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum("user", "generated", name="comparisonpromptsource"),
            nullable=False,
        ),
        sa.Column("text_en", sa.Text(), nullable=True),
        sa.Column("text_zh", sa.Text(), nullable=True),
        sa.Column("language_original", sa.Enum("en", "zh", name="promptlanguage"), nullable=False, server_default=sa.text("'zh'")),
        sa.Column("primary_brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=True),
        sa.Column("competitor_brand_id", sa.Integer(), sa.ForeignKey("brands.id"), nullable=True),
        sa.Column("primary_product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("competitor_product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("aspects", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_comparison_prompts_run_id", "comparison_prompts", ["run_id"], unique=False)

    op.create_table(
        "comparison_answers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("comparison_prompt_id", sa.Integer(), sa.ForeignKey("comparison_prompts.id"), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("route", sa.Enum("local", "vendor", "openrouter", name="llmroute"), nullable=True),
        sa.Column("raw_answer_zh", sa.Text(), nullable=False),
        sa.Column("raw_answer_en", sa.Text(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("latency", sa.Float(), nullable=True),
        sa.Column("cost_estimate", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("run_id", "comparison_prompt_id", name="uq_comparison_answers_run_prompt"),
    )
    op.create_index("ix_comparison_answers_run_id", "comparison_answers", ["run_id"], unique=False)

    op.create_table(
        "comparison_sentiment_observations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("comparison_answer_id", sa.Integer(), sa.ForeignKey("comparison_answers.id"), nullable=False),
        sa.Column("entity_type", sa.Enum("brand", "product", name="entitytype"), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column(
            "entity_role",
            sa.Enum("primary", "competitor", name="comparisonentityrole"),
            nullable=False,
        ),
        sa.Column("aspect", sa.String(length=255), nullable=True),
        sa.Column("sentiment", sa.Enum("positive", "neutral", "negative", name="sentiment"), nullable=False),
        sa.Column("snippet_zh", sa.Text(), nullable=False),
        sa.Column("snippet_en", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_comparison_sentiment_observations_run_entity",
        "comparison_sentiment_observations",
        ["run_id", "entity_type", "entity_id"],
        unique=False,
    )

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
    op.create_index("ix_comparison_run_events_run_id", "comparison_run_events", ["run_id"], unique=False)

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
