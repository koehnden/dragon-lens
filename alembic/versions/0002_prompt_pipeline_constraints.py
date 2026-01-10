"""add prompt pipeline constraints

Revision ID: 0002
Revises: 0001
Create Date: 2026-01-07
"""

from __future__ import annotations

from alembic import op


revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("llm_answers") as batch_op:
        batch_op.create_unique_constraint(
            "uq_llm_answers_run_prompt",
            ["run_id", "prompt_id"],
        )
    with op.batch_alter_table("brands") as batch_op:
        batch_op.create_unique_constraint(
            "uq_brands_vertical_display",
            ["vertical_id", "display_name"],
        )
    with op.batch_alter_table("products") as batch_op:
        batch_op.create_unique_constraint(
            "uq_products_vertical_display",
            ["vertical_id", "display_name"],
        )
    op.create_index("ix_prompts_run_id", "prompts", ["run_id"], unique=False)
    op.create_index("ix_brand_mentions_llm_answer_id", "brand_mentions", ["llm_answer_id"], unique=False)
    op.create_index("ix_product_mentions_llm_answer_id", "product_mentions", ["llm_answer_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_product_mentions_llm_answer_id", table_name="product_mentions")
    op.drop_index("ix_brand_mentions_llm_answer_id", table_name="brand_mentions")
    op.drop_index("ix_prompts_run_id", table_name="prompts")
    op.drop_constraint("uq_products_vertical_display", "products", type_="unique")
    op.drop_constraint("uq_brands_vertical_display", "brands", type_="unique")
    op.drop_constraint("uq_llm_answers_run_prompt", "llm_answers", type_="unique")
