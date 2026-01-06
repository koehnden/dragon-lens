from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import (
    Brand,
    BrandMention,
    LLMAnswer,
    Product,
    ProductBrandMapping,
    ProductMention,
    Prompt,
    Run,
    Vertical,
)
from models.domain import PromptLanguage, RunStatus, Sentiment


def test_get_run_entities(client: TestClient, db_session: Session):
    vertical = Vertical(name="Entities Vertical")
    db_session.add(vertical)
    db_session.flush()

    run = Run(
        vertical_id=vertical.id,
        provider="qwen",
        model_name="qwen2.5:7b",
        status=RunStatus.COMPLETED,
    )
    db_session.add(run)
    db_session.flush()

    prompt = Prompt(
        vertical_id=vertical.id,
        run_id=run.id,
        text_zh="测试",
        language_original=PromptLanguage.ZH,
    )
    db_session.add(prompt)
    db_session.flush()

    answer = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt.id,
        raw_answer_zh="Toyota RAV4",
    )
    db_session.add(answer)
    db_session.flush()

    brand = Brand(
        vertical_id=vertical.id,
        display_name="Toyota",
        original_name="Toyota",
        aliases={"zh": [], "en": []},
        is_user_input=True,
    )
    db_session.add(brand)
    db_session.flush()

    product = Product(
        vertical_id=vertical.id,
        brand_id=brand.id,
        display_name="RAV4",
        original_name="RAV4",
        is_user_input=False,
    )
    db_session.add(product)
    db_session.flush()

    db_session.add(BrandMention(
        llm_answer_id=answer.id,
        brand_id=brand.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={"zh": ["Toyota"], "en": []},
    ))
    db_session.add(ProductMention(
        llm_answer_id=answer.id,
        product_id=product.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={"zh": ["RAV4"], "en": []},
    ))
    db_session.add(ProductBrandMapping(
        vertical_id=vertical.id,
        product_id=product.id,
        brand_id=brand.id,
        confidence=0.9,
        is_validated=False,
        source="qwen",
    ))
    db_session.commit()

    response = client.get(f"/api/v1/tracking/runs/{run.id}/entities")

    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run.id
    assert data["vertical_id"] == vertical.id
    assert data["vertical_name"] == "Entities Vertical"
    assert len(data["brands"]) == 1
    assert len(data["products"]) == 1
    assert len(data["mappings"]) == 1
    assert data["brands"][0]["brand_name"] == "Toyota"
    assert data["brands"][0]["mention_count"] == 1
    assert data["products"][0]["product_name"] == "RAV4"
    assert data["products"][0]["mention_count"] == 1
    assert data["mappings"][0]["product_id"] == product.id
    assert data["mappings"][0]["brand_id"] == brand.id


def test_get_run_entities_missing_run(client: TestClient):
    response = client.get("/api/v1/tracking/runs/99999/entities")
    assert response.status_code == 404
