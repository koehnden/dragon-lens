"""add feature extraction tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-01-13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


sentiment_enum = postgresql.ENUM("POSITIVE", "NEUTRAL", "NEGATIVE", name="sentiment", create_type=False)
entitytype_enum = postgresql.ENUM("BRAND", "PRODUCT", name="entitytype", create_type=False)


def upgrade() -> None:
    op.create_table(
        "features",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("vertical_id", sa.Integer(), sa.ForeignKey("verticals.id"), nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("display_name_zh", sa.String(255), nullable=False),
        sa.Column("display_name_en", sa.String(255), nullable=True),
        sa.Column("mention_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "feature_aliases",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("feature_id", sa.Integer(), sa.ForeignKey("features.id"), nullable=False),
        sa.Column("alias", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "feature_mentions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("feature_id", sa.Integer(), sa.ForeignKey("features.id"), nullable=False),
        sa.Column("brand_mention_id", sa.Integer(), sa.ForeignKey("brand_mentions.id"), nullable=True),
        sa.Column("product_mention_id", sa.Integer(), sa.ForeignKey("product_mentions.id"), nullable=True),
        sa.Column("snippet_zh", sa.Text(), nullable=False),
        sa.Column("snippet_en", sa.Text(), nullable=True),
        sa.Column("sentiment", sentiment_enum, nullable=False, server_default="NEUTRAL"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "run_feature_metrics",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_id", sa.Integer(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("entity_type", entitytype_enum, nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), sa.ForeignKey("features.id"), nullable=False),
        sa.Column("frequency", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("positive_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("neutral_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("negative_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("combined_score", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_index("ix_features_vertical_id", "features", ["vertical_id"], unique=False)
    op.create_index("ix_feature_aliases_feature_id", "feature_aliases", ["feature_id"], unique=False)
    op.create_index("ix_feature_mentions_feature_id", "feature_mentions", ["feature_id"], unique=False)
    op.create_index("ix_feature_mentions_brand_mention_id", "feature_mentions", ["brand_mention_id"], unique=False)
    op.create_index("ix_feature_mentions_product_mention_id", "feature_mentions", ["product_mention_id"], unique=False)
    op.create_index("ix_run_feature_metrics_run_id", "run_feature_metrics", ["run_id"], unique=False)
    op.create_index("ix_run_feature_metrics_feature_id", "run_feature_metrics", ["feature_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_run_feature_metrics_feature_id", table_name="run_feature_metrics")
    op.drop_index("ix_run_feature_metrics_run_id", table_name="run_feature_metrics")
    op.drop_index("ix_feature_mentions_product_mention_id", table_name="feature_mentions")
    op.drop_index("ix_feature_mentions_brand_mention_id", table_name="feature_mentions")
    op.drop_index("ix_feature_mentions_feature_id", table_name="feature_mentions")
    op.drop_index("ix_feature_aliases_feature_id", table_name="feature_aliases")
    op.drop_index("ix_features_vertical_id", table_name="features")

    op.drop_table("run_feature_metrics")
    op.drop_table("feature_mentions")
    op.drop_table("feature_aliases")
    op.drop_table("features")
