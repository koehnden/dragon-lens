import json

import pytest


def _create_vertical(db_session, name: str):
    from models import Vertical
    vertical = Vertical(name=name)
    db_session.add(vertical)
    db_session.flush()
    return vertical


def _create_run(db_session, vertical_id: int):
    from models import Run
    run = Run(vertical_id=vertical_id, provider="qwen", model_name="qwen")
    db_session.add(run)
    db_session.flush()
    return run


def _create_prompt(db_session, vertical_id: int):
    from models import Prompt
    prompt = Prompt(vertical_id=vertical_id, text_zh="test")
    db_session.add(prompt)
    db_session.flush()
    return prompt


def _create_answer(db_session, run_id: int, prompt_id: int, text: str):
    from models import LLMAnswer
    answer = LLMAnswer(run_id=run_id, prompt_id=prompt_id, provider="qwen", model_name="qwen", raw_answer_zh=text, raw_answer_en=None)
    db_session.add(answer)
    db_session.flush()
    return answer


def _create_debug(db_session, answer_id: int, brands: list[str], products: list[str]) -> None:
    from models import ExtractionDebug
    debug = ExtractionDebug(llm_answer_id=answer_id, raw_brands=json.dumps(brands), raw_products=json.dumps(products), rejected_at_light_filter=json.dumps([]), final_brands=json.dumps(brands), final_products=json.dumps(products), extraction_method="qwen")
    db_session.add(debug)


def _create_brand(db_session, vertical_id: int, name: str):
    from models import Brand
    brand = Brand(vertical_id=vertical_id, display_name=name, original_name=name, translated_name=None, aliases={"zh": [], "en": []}, is_user_input=True)
    db_session.add(brand)
    db_session.flush()
    return brand


def _create_product(db_session, vertical_id: int, name: str):
    from models import Product
    product = Product(vertical_id=vertical_id, brand_id=None, display_name=name, original_name=name, translated_name=None, is_user_input=False)
    db_session.add(product)
    db_session.flush()
    return product


def _create_rejected_brand(db_session, vertical_id: int, name: str, reason: str) -> None:
    from models import EntityType, RejectedEntity
    rejected = RejectedEntity(vertical_id=vertical_id, entity_type=EntityType.BRAND, name=name, rejection_reason=reason)
    db_session.add(rejected)


def _setup_rejected_brand_case(db_session) -> tuple[int, int]:
    vertical = _create_vertical(db_session, "Cars")
    run = _create_run(db_session, vertical.id); prompt = _create_prompt(db_session, vertical.id)
    answer = _create_answer(db_session, run.id, prompt.id, "Orion Nova X2")
    _create_debug(db_session, answer.id, ["Orion"], ["Nova X2"])
    _create_brand(db_session, vertical.id, "Orion"); product = _create_product(db_session, vertical.id, "Nova X2")
    _create_rejected_brand(db_session, vertical.id, "Orion", "rejected_at_list_filter")
    db_session.commit()
    return run.id, product.id


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


@pytest.mark.asyncio
async def test_map_products_to_brands_for_run_skips_rejected_brand(db_session):
    from unittest.mock import patch
    from models import Product
    from services.brand_recognition.product_brand_mapping import map_products_to_brands_for_run

    run_id, product_id = _setup_rejected_brand_case(db_session)

    with patch(
        "services.brand_recognition.product_brand_mapping._rejected_brand_names"
    ) as mock_rejected:
        mock_rejected.return_value = {"orion"}
        await map_products_to_brands_for_run(db_session, run_id)

    product = db_session.query(Product).filter(Product.id == product_id).first()
    assert product.brand_id is None
