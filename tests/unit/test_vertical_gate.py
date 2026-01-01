import json
from unittest.mock import AsyncMock, patch

import pytest

from models import Brand, BrandMention, LLMAnswer, Product, ProductMention, Prompt, RejectedEntity, Run, Vertical
from models.domain import EntityType, PromptLanguage, RunStatus, Sentiment
from services.brand_recognition.vertical_gate import apply_vertical_gate_to_run


def _create_run_with_answer(db_session):
    vertical = Vertical(name="Diapers", description="Diaper purchase prompts")
    db_session.add(vertical)
    db_session.flush()

    run = Run(vertical_id=vertical.id, provider="qwen", model_name="qwen", status=RunStatus.COMPLETED)
    db_session.add(run)
    db_session.flush()

    prompt = Prompt(
        vertical_id=vertical.id,
        run_id=run.id,
        text_zh="推荐纸尿裤品牌TOP10",
        language_original=PromptLanguage.ZH,
    )
    db_session.add(prompt)
    db_session.flush()

    answer = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt.id,
        provider="qwen",
        model_name="qwen",
        raw_answer_zh="1. Pampers 2. Mothercare",
    )
    db_session.add(answer)
    db_session.flush()
    return vertical, run, prompt, answer


@pytest.mark.asyncio
async def test_vertical_gate_rejects_discovered_brand_and_cascades_to_products(db_session):
    vertical, run, _, answer = _create_run_with_answer(db_session)

    user_brand = Brand(
        vertical_id=vertical.id,
        display_name="Pampers",
        original_name="Pampers",
        translated_name=None,
        aliases={"zh": ["帮宝适"], "en": ["Pampers"]},
        is_user_input=True,
    )
    discovered_brand = Brand(
        vertical_id=vertical.id,
        display_name="Mothercare",
        original_name="Mothercare",
        translated_name=None,
        aliases={"zh": [], "en": []},
        is_user_input=False,
    )
    db_session.add_all([user_brand, discovered_brand])
    db_session.flush()

    product = Product(
        vertical_id=vertical.id,
        brand_id=discovered_brand.id,
        display_name="Some Diaper",
        original_name="Some Diaper",
        translated_name=None,
        is_user_input=False,
    )
    db_session.add(product)
    db_session.flush()

    user_mention = BrandMention(
        llm_answer_id=answer.id,
        brand_id=user_brand.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={"zh": ["Pampers很不错"], "en": []},
    )
    discovered_mention = BrandMention(
        llm_answer_id=answer.id,
        brand_id=discovered_brand.id,
        mentioned=True,
        rank=2,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={"zh": ["Mothercare在母婴店常见"], "en": []},
    )
    product_mention = ProductMention(
        llm_answer_id=answer.id,
        product_id=product.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={"zh": ["Some Diaper"], "en": []},
    )
    db_session.add_all([user_mention, discovered_mention, product_mention])
    db_session.flush()

    response = json.dumps(
        {"results": [{"brand": "Mothercare", "relevant": False, "reason": "retailer"}]},
        ensure_ascii=False,
    )

    with patch(
        "services.brand_recognition.vertical_gate.OllamaService._call_ollama",
        new=AsyncMock(return_value=response),
    ):
        rejected = await apply_vertical_gate_to_run(db_session, run.id)

    assert rejected == 1

    kept = db_session.query(BrandMention).filter(BrandMention.brand_id == user_brand.id).first()
    assert kept is not None
    assert kept.mentioned is True

    rejected_brand = db_session.query(BrandMention).filter(BrandMention.brand_id == discovered_brand.id).first()
    assert rejected_brand is not None
    assert rejected_brand.mentioned is False

    rejected_product = db_session.query(ProductMention).filter(ProductMention.product_id == product.id).first()
    assert rejected_product is not None
    assert rejected_product.mentioned is False

    stored = db_session.query(RejectedEntity).filter(
        RejectedEntity.vertical_id == vertical.id,
        RejectedEntity.entity_type == EntityType.BRAND,
        RejectedEntity.name == "Mothercare",
        RejectedEntity.rejection_reason == "off_vertical",
    ).first()
    assert stored is not None
    assert stored.example_context


@pytest.mark.asyncio
async def test_vertical_gate_keeps_on_parse_failure(db_session):
    _, run, _, answer = _create_run_with_answer(db_session)

    discovered_brand = Brand(
        vertical_id=run.vertical_id,
        display_name="Mothercare",
        original_name="Mothercare",
        translated_name=None,
        aliases={"zh": [], "en": []},
        is_user_input=False,
    )
    db_session.add(discovered_brand)
    db_session.flush()

    mention = BrandMention(
        llm_answer_id=answer.id,
        brand_id=discovered_brand.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={"zh": ["Mothercare在母婴店常见"], "en": []},
    )
    db_session.add(mention)
    db_session.flush()

    with patch(
        "services.brand_recognition.vertical_gate.OllamaService._call_ollama",
        new=AsyncMock(return_value="not json"),
    ):
        rejected = await apply_vertical_gate_to_run(db_session, run.id)

    assert rejected == 0
    refreshed = db_session.query(BrandMention).filter(BrandMention.brand_id == discovered_brand.id).first()
    assert refreshed is not None
    assert refreshed.mentioned is True
