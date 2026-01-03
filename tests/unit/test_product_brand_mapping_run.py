import json

import pytest


@pytest.mark.asyncio
async def test_map_products_to_brands_for_run_updates_product_brand(db_session):
    from models import Brand, ExtractionDebug, LLMAnswer, Product, Prompt, Run, Vertical
    from services.brand_recognition.product_brand_mapping import map_products_to_brands_for_run

    vertical = Vertical(name="Cars")
    db_session.add(vertical)
    db_session.flush()
    run = Run(vertical_id=vertical.id, provider="qwen", model_name="qwen")
    prompt = Prompt(vertical_id=vertical.id, text_zh="test")
    db_session.add_all([run, prompt])
    db_session.flush()
    answer = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt.id,
        provider="qwen",
        model_name="qwen",
        raw_answer_zh="1. Orion Nova X2 is a solid choice.",
        raw_answer_en=None,
    )
    db_session.add(answer)
    db_session.flush()
    debug = ExtractionDebug(
        llm_answer_id=answer.id,
        raw_brands=json.dumps(["Orion"]),
        raw_products=json.dumps(["Nova X2"]),
        rejected_at_light_filter=json.dumps([]),
        final_brands=json.dumps(["Orion"]),
        final_products=json.dumps(["Nova X2"]),
        extraction_method="qwen",
    )
    db_session.add(debug)
    brand = Brand(
        vertical_id=vertical.id,
        display_name="Orion",
        original_name="Orion",
        translated_name=None,
        aliases={"zh": [], "en": []},
        is_user_input=True,
    )
    product = Product(
        vertical_id=vertical.id,
        brand_id=None,
        display_name="Nova X2",
        original_name="Nova X2",
        translated_name=None,
        is_user_input=False,
    )
    db_session.add_all([brand, product])
    db_session.commit()

    await map_products_to_brands_for_run(db_session, run.id)
    db_session.refresh(product)

    assert product.brand_id == brand.id
