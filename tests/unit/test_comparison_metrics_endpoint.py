from datetime import datetime

from fastapi.testclient import TestClient

from models import (
    Brand,
    ComparisonAnswer,
    ComparisonEntityRole,
    ComparisonPrompt,
    ComparisonPromptSource,
    ComparisonPromptType,
    ComparisonRunEvent,
    ComparisonRunStatus,
    ComparisonSentimentObservation,
    EntityType,
    Product,
    Run,
    RunComparisonConfig,
    RunProductMetrics,
    RunStatus,
    Sentiment,
    Vertical,
)


def test_run_comparison_metrics_409_when_not_ready(client: TestClient, db_session):
    vertical = Vertical(name="V", description=None)
    db_session.add(vertical)
    db_session.commit()
    db_session.refresh(vertical)
    brand = Brand(vertical_id=vertical.id, display_name="A", original_name="A", translated_name=None, aliases={"zh": [], "en": []})
    db_session.add(brand)
    db_session.commit()
    db_session.refresh(brand)
    run = Run(vertical_id=vertical.id, provider="qwen", model_name="qwen2.5:7b-instruct-q4_0", status=RunStatus.COMPLETED)
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    db_session.add(RunComparisonConfig(run_id=run.id, vertical_id=vertical.id, primary_brand_id=brand.id, enabled=True, competitor_brands=["B"]))
    db_session.commit()
    response = client.get(f"/api/v1/metrics/run/{run.id}/comparison")
    assert response.status_code == 409


def test_run_comparison_metrics_returns_summaries(client: TestClient, db_session):
    vertical = Vertical(name="V2", description=None)
    db_session.add(vertical)
    db_session.commit()
    db_session.refresh(vertical)
    primary = Brand(vertical_id=vertical.id, display_name="A", original_name="A", translated_name=None, aliases={"zh": [], "en": []})
    competitor = Brand(vertical_id=vertical.id, display_name="B", original_name="B", translated_name=None, aliases={"zh": [], "en": []})
    product_a = Product(vertical_id=vertical.id, brand_id=None, display_name="P1", original_name="P1", translated_name=None)
    db_session.add_all([primary, competitor, product_a])
    db_session.commit()
    for obj in [primary, competitor, product_a]:
        db_session.refresh(obj)
    run = Run(vertical_id=vertical.id, provider="qwen", model_name="qwen2.5:7b-instruct-q4_0", status=RunStatus.COMPLETED, run_time=datetime.utcnow())
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    config = RunComparisonConfig(run_id=run.id, vertical_id=vertical.id, primary_brand_id=primary.id, enabled=True, competitor_brands=["B"], status=ComparisonRunStatus.COMPLETED)
    db_session.add(config)
    db_session.commit()
    prompt = ComparisonPrompt(
        run_id=run.id,
        vertical_id=vertical.id,
        prompt_type=ComparisonPromptType.BRAND_VS_BRAND,
        source=ComparisonPromptSource.USER,
        text_zh="A vs B?",
        text_en="A vs B?",
        primary_brand_id=primary.id,
        competitor_brand_id=competitor.id,
    )
    db_session.add(prompt)
    db_session.commit()
    db_session.refresh(prompt)
    answer = ComparisonAnswer(
        run_id=run.id,
        comparison_prompt_id=prompt.id,
        provider=run.provider,
        model_name=run.model_name,
        raw_answer_zh="A 不错, B 一般",
        raw_answer_en="A is good, B is average",
    )
    db_session.add(answer)
    db_session.commit()
    db_session.refresh(answer)
    db_session.add_all([
        ComparisonSentimentObservation(
            run_id=run.id,
            comparison_answer_id=answer.id,
            entity_type=EntityType.BRAND,
            entity_id=primary.id,
            entity_role=ComparisonEntityRole.PRIMARY,
            sentiment=Sentiment.POSITIVE,
            snippet_zh="A 不错",
            snippet_en="A is good",
        ),
        ComparisonSentimentObservation(
            run_id=run.id,
            comparison_answer_id=answer.id,
            entity_type=EntityType.BRAND,
            entity_id=competitor.id,
            entity_role=ComparisonEntityRole.COMPETITOR,
            sentiment=Sentiment.NEGATIVE,
            snippet_zh="B 一般",
            snippet_en="B is average",
        ),
        ComparisonRunEvent(run_id=run.id, level="info", code="x", message="m", payload=None),
        RunProductMetrics(
            run_id=run.id,
            product_id=product_a.id,
            mention_rate=0.0,
            share_of_voice=0.0,
            top_spot_share=0.0,
            sentiment_index=0.0,
            dragon_lens_visibility=0.0,
        ),
    ])
    db_session.commit()
    response = client.get(f"/api/v1/metrics/run/{run.id}/comparison?include_snippets=true")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run.id
    assert data["primary_brand_id"] == primary.id
    assert len(data["brands"]) == 2
    assert data["messages"][0]["message"] == "m"


def test_run_product_metrics_returns_products(client: TestClient, db_session):
    vertical = Vertical(name="V3", description=None)
    db_session.add(vertical)
    db_session.commit()
    db_session.refresh(vertical)
    product = Product(vertical_id=vertical.id, brand_id=None, display_name="P", original_name="P", translated_name=None)
    db_session.add(product)
    db_session.commit()
    db_session.refresh(product)
    run = Run(vertical_id=vertical.id, provider="qwen", model_name="qwen2.5:7b-instruct-q4_0", status=RunStatus.COMPLETED, run_time=datetime.utcnow())
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    db_session.add(RunProductMetrics(
        run_id=run.id,
        product_id=product.id,
        mention_rate=0.1,
        share_of_voice=0.2,
        top_spot_share=0.3,
        sentiment_index=0.4,
        dragon_lens_visibility=0.5,
    ))
    db_session.commit()
    response = client.get(f"/api/v1/metrics/run/{run.id}/products")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run.id
    assert data["products"][0]["product_name"]
