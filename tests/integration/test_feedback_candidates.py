from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import (
    Brand,
    BrandMention,
    LLMAnswer,
    Prompt,
    PromptLanguage,
    Product,
    ProductBrandMapping,
    ProductMention,
    Run,
    RunStatus,
    Vertical,
)
from models.knowledge_domain import KnowledgeVerticalAlias


def test_feedback_candidates_disappear_after_feedback(
    client: TestClient,
    db_session: Session,
):
    vertical = Vertical(name="SUV Cars", description="SUV segment")
    db_session.add(vertical)
    db_session.commit()

    brand = Brand(
        vertical_id=vertical.id,
        display_name="丰田",
        original_name="丰田",
        translated_name="Toyota",
        aliases={"zh": [], "en": []},
        is_user_input=True,
    )
    product = Product(
        vertical_id=vertical.id,
        brand_id=None,
        display_name="卡罗拉",
        original_name="卡罗拉",
        translated_name="Corolla",
        is_user_input=False,
    )
    db_session.add(brand)
    db_session.add(product)
    db_session.commit()

    run = Run(vertical_id=vertical.id, provider="qwen", model_name="qwen", status=RunStatus.COMPLETED)
    db_session.add(run)
    db_session.commit()

    prompt = Prompt(vertical_id=vertical.id, run_id=run.id, text_zh="x", text_en=None, language_original=PromptLanguage.ZH)
    db_session.add(prompt)
    db_session.commit()

    answer = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt.id,
        raw_answer_zh="x",
        raw_answer_en=None,
        tokens_in=0,
        tokens_out=0,
        provider="qwen",
        model_name="qwen",
    )
    db_session.add(answer)
    db_session.commit()

    db_session.add(BrandMention(llm_answer_id=answer.id, brand_id=brand.id, mentioned=True))
    db_session.add(ProductMention(llm_answer_id=answer.id, product_id=product.id, mentioned=True, rank=1))
    db_session.add(
        ProductBrandMapping(
            vertical_id=vertical.id,
            product_id=product.id,
            brand_id=brand.id,
            confidence=0.9,
            is_validated=False,
            source="qwen",
        )
    )
    db_session.commit()

    candidates = client.get("/api/v1/feedback/candidates", params={"vertical_id": vertical.id})
    assert candidates.status_code == 200
    data = candidates.json()
    assert data["vertical_id"] == vertical.id
    assert data["latest_completed_run_id"] == run.id
    assert any(item["name"] == "丰田" for item in data["brands"])
    assert any(item["name"] == "卡罗拉" for item in data["products"])
    assert any(item["product_name"] == "卡罗拉" and item["brand_name"] == "丰田" for item in data["mappings"])
    assert any(item["canonical_name"] == "丰田" for item in data["translations"])
    assert any(item["canonical_name"] == "卡罗拉" for item in data["translations"])

    payload = {
        "run_id": data["latest_completed_run_id"],
        "vertical_id": vertical.id,
        "canonical_vertical": {"is_new": True, "name": "Cars"},
        "mapping_feedback": [{"action": "validate", "product_name": "卡罗拉", "brand_name": "丰田"}],
        "translation_overrides": [
            {"entity_type": "brand", "canonical_name": "丰田", "language": "en", "override_text": "Toyota"},
            {"entity_type": "product", "canonical_name": "卡罗拉", "language": "en", "override_text": "Corolla"},
        ],
    }
    submitted = client.post("/api/v1/feedback/submit", json=payload)
    assert submitted.status_code == 200

    after = client.get("/api/v1/feedback/candidates", params={"vertical_id": vertical.id})
    assert after.status_code == 200
    after_data = after.json()
    assert after_data["brands"] == []
    assert after_data["products"] == []
    assert after_data["mappings"] == []
    assert after_data["translations"] == []


def test_feedback_candidates_aggregate_across_mapped_verticals(
    client: TestClient,
    db_session: Session,
):
    vertical_a = Vertical(name="SUV Cars", description="SUV")
    vertical_b = Vertical(name="Family Cars", description="Family")
    db_session.add_all([vertical_a, vertical_b])
    db_session.commit()

    run_a = Run(vertical_id=vertical_a.id, provider="qwen", model_name="qwen", status=RunStatus.COMPLETED)
    run_b = Run(vertical_id=vertical_b.id, provider="qwen", model_name="qwen", status=RunStatus.COMPLETED)
    db_session.add_all([run_a, run_b])
    db_session.commit()

    prompt_a = Prompt(vertical_id=vertical_a.id, run_id=run_a.id, text_zh="x", text_en=None, language_original=PromptLanguage.ZH)
    prompt_b = Prompt(vertical_id=vertical_b.id, run_id=run_b.id, text_zh="x", text_en=None, language_original=PromptLanguage.ZH)
    db_session.add_all([prompt_a, prompt_b])
    db_session.commit()

    brand_a = Brand(vertical_id=vertical_a.id, display_name="丰田", original_name="丰田", translated_name="Toyota", aliases={"zh": [], "en": []}, is_user_input=True)
    brand_b = Brand(vertical_id=vertical_b.id, display_name="本田", original_name="本田", translated_name="Honda", aliases={"zh": [], "en": []}, is_user_input=True)
    product_a = Product(vertical_id=vertical_a.id, brand_id=None, display_name="卡罗拉", original_name="卡罗拉", translated_name="Corolla", is_user_input=False)
    product_b = Product(vertical_id=vertical_b.id, brand_id=None, display_name="思域", original_name="思域", translated_name="Civic", is_user_input=False)
    db_session.add_all([brand_a, brand_b, product_a, product_b])
    db_session.commit()

    answer_a = LLMAnswer(run_id=run_a.id, prompt_id=prompt_a.id, raw_answer_zh="x", raw_answer_en=None, tokens_in=0, tokens_out=0, provider="qwen", model_name="qwen")
    answer_b = LLMAnswer(run_id=run_b.id, prompt_id=prompt_b.id, raw_answer_zh="x", raw_answer_en=None, tokens_in=0, tokens_out=0, provider="qwen", model_name="qwen")
    db_session.add_all([answer_a, answer_b])
    db_session.commit()

    db_session.add(BrandMention(llm_answer_id=answer_a.id, brand_id=brand_a.id, mentioned=True))
    db_session.add(BrandMention(llm_answer_id=answer_b.id, brand_id=brand_b.id, mentioned=True))
    db_session.add(ProductMention(llm_answer_id=answer_a.id, product_id=product_a.id, mentioned=True, rank=1))
    db_session.add(ProductMention(llm_answer_id=answer_b.id, product_id=product_b.id, mentioned=True, rank=1))
    db_session.commit()

    mapped = client.post("/api/v1/feedback/vertical-alias", json={"vertical_id": vertical_a.id, "canonical_vertical": {"is_new": True, "name": "Cars"}})
    assert mapped.status_code == 200
    canonical_id = mapped.json()["canonical_vertical_id"]

    mapped_b = client.post("/api/v1/feedback/vertical-alias", json={"vertical_id": vertical_b.id, "canonical_vertical": {"is_new": False, "id": canonical_id}})
    assert mapped_b.status_code == 200

    candidates = client.get("/api/v1/feedback/candidates", params={"vertical_id": vertical_a.id})
    assert candidates.status_code == 200
    data = candidates.json()
    assert any(item["name"] == "丰田" for item in data["brands"])
    assert any(item["name"] == "本田" for item in data["brands"])
    assert any(item["name"] == "卡罗拉" for item in data["products"])
    assert any(item["name"] == "思域" for item in data["products"])
