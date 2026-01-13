import pytest

from models import (
    Brand,
    BrandMention,
    LLMAnswer,
    Product,
    ProductBrandMapping,
    ProductMention,
    Run,
    RunStatus,
    Sentiment,
    Vertical,
)


def test_run_export_groups_products_by_brand(client, db_session):
    vertical = Vertical(name="phones", description=None)
    db_session.add(vertical)
    db_session.commit()

    brand = Brand(
        vertical_id=vertical.id,
        display_name="耐克",
        original_name="耐克",
        translated_name="Nike",
        aliases={},
        is_user_input=False,
    )
    other_brand = Brand(
        vertical_id=vertical.id,
        display_name="阿迪达斯",
        original_name="阿迪达斯",
        translated_name="Adidas",
        aliases={},
        is_user_input=False,
    )
    db_session.add_all([brand, other_brand])
    db_session.commit()

    run = Run(
        vertical_id=vertical.id,
        provider="qwen",
        model_name="qwen2",
        status=RunStatus.COMPLETED,
        reuse_answers=False,
        web_search_enabled=False,
    )
    db_session.add(run)
    db_session.commit()

    from models import Prompt

    prompt = Prompt(
        vertical_id=vertical.id,
        run_id=run.id,
        text_zh="推荐运动鞋品牌",
        text_en="Recommend sports shoe brands",
    )
    db_session.add(prompt)
    db_session.commit()

    answer = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt.id,
        provider="qwen",
        model_name="qwen2",
        raw_answer_zh="耐克和阿迪达斯都不错。",
        raw_answer_en="Nike and Adidas are both good.",
    )
    db_session.add(answer)
    db_session.commit()

    db_session.add_all(
        [
            BrandMention(
                llm_answer_id=answer.id,
                brand_id=brand.id,
                mentioned=True,
                rank=1,
                sentiment=Sentiment.NEUTRAL,
                evidence_snippets={"zh": ["耐克"], "en": ["Nike"]},
            ),
            BrandMention(
                llm_answer_id=answer.id,
                brand_id=other_brand.id,
                mentioned=True,
                rank=2,
                sentiment=Sentiment.NEUTRAL,
                evidence_snippets={"zh": ["阿迪达斯"], "en": ["Adidas"]},
            ),
        ]
    )
    db_session.commit()

    direct_product = Product(
        vertical_id=vertical.id,
        brand_id=brand.id,
        display_name="耐克Air Max",
        original_name="耐克Air Max",
        translated_name="Nike Air Max",
        is_user_input=False,
    )
    mapped_product = Product(
        vertical_id=vertical.id,
        brand_id=None,
        display_name="Air Zoom",
        original_name="Air Zoom",
        translated_name="Air Zoom",
        is_user_input=False,
    )
    db_session.add_all([direct_product, mapped_product])
    db_session.commit()

    db_session.add(
        ProductBrandMapping(
            vertical_id=vertical.id,
            product_id=mapped_product.id,
            brand_id=brand.id,
            confidence=0.9,
            is_validated=True,
            source="test",
        )
    )
    db_session.commit()

    db_session.add_all(
        [
            ProductMention(
                llm_answer_id=answer.id,
                product_id=direct_product.id,
                mentioned=True,
                rank=1,
                sentiment=Sentiment.NEUTRAL,
                evidence_snippets={"zh": ["Air Max"], "en": ["Air Max"]},
            ),
            ProductMention(
                llm_answer_id=answer.id,
                product_id=mapped_product.id,
                mentioned=True,
                rank=2,
                sentiment=Sentiment.NEUTRAL,
                evidence_snippets={"zh": ["Air Zoom"], "en": ["Air Zoom"]},
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/api/v1/tracking/runs/{run.id}/inspector-export")
    assert response.status_code == 200

    payload = response.json()
    assert isinstance(payload, list)
    assert len(payload) == 1
    item = payload[0]
    assert item["vertical_name"] == "phones"
    assert item["model"] == "qwen2"
    assert item["prompt_zh"] == "推荐运动鞋品牌"
    assert item["prompt_eng"] == "Recommend sports shoe brands"
    assert item["prompt_response_zh"] == "耐克和阿迪达斯都不错。"
    assert item["prompt_response_en"] == "Nike and Adidas are both good."
    assert item["run_id"] == run.id
    assert item["llm_answer_id"] == answer.id

    extracted = item["brands_extracted"]
    assert {b["brand_en"] for b in extracted} == {"Nike", "Adidas"}
    nike = next(b for b in extracted if b["brand_en"] == "Nike")
    assert nike["rank"] == 1
    assert nike["text_snippet_zh"] == "耐克"
    assert nike["text_snippet_en"] == "Nike"
    assert set(nike["products_en"]) == {"Nike Air Max", "Air Zoom"}
    adidas = next(b for b in extracted if b["brand_en"] == "Adidas")
    assert adidas["products_zh"] == []


def test_vertical_export_includes_only_completed_runs(client, db_session):
    vertical = Vertical(name="cars", description=None)
    db_session.add(vertical)
    db_session.commit()

    run_ok = Run(
        vertical_id=vertical.id,
        provider="qwen",
        model_name="qwen2",
        status=RunStatus.COMPLETED,
        reuse_answers=False,
        web_search_enabled=False,
    )
    run_failed = Run(
        vertical_id=vertical.id,
        provider="qwen",
        model_name="qwen2",
        status=RunStatus.FAILED,
        reuse_answers=False,
        web_search_enabled=False,
    )
    db_session.add_all([run_ok, run_failed])
    db_session.commit()

    from models import Prompt

    prompt_ok = Prompt(vertical_id=vertical.id, run_id=run_ok.id, text_zh="ok", text_en="ok")
    prompt_failed = Prompt(vertical_id=vertical.id, run_id=run_failed.id, text_zh="bad", text_en="bad")
    db_session.add_all([prompt_ok, prompt_failed])
    db_session.commit()

    db_session.add_all(
        [
            LLMAnswer(
                run_id=run_ok.id,
                prompt_id=prompt_ok.id,
                provider="qwen",
                model_name="qwen2",
                raw_answer_zh="ok",
                raw_answer_en="ok",
            ),
            LLMAnswer(
                run_id=run_failed.id,
                prompt_id=prompt_failed.id,
                provider="qwen",
                model_name="qwen2",
                raw_answer_zh="bad",
                raw_answer_en="bad",
            ),
        ]
    )
    db_session.commit()

    response = client.get(f"/api/v1/verticals/{vertical.id}/inspector-export")
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 1
    assert payload[0]["run_id"] == run_ok.id

