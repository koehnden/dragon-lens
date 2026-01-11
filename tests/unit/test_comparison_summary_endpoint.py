from datetime import datetime

from fastapi.testclient import TestClient

from models import (
    Brand,
    ComparisonAnswer,
    ComparisonEntityRole,
    ComparisonPrompt,
    ComparisonPromptSource,
    ComparisonPromptType,
    ComparisonRunStatus,
    ComparisonSentimentObservation,
    EntityType,
    Product,
    Run,
    RunComparisonConfig,
    RunStatus,
    Sentiment,
    Vertical,
)


def test_run_comparison_summary_409_when_not_ready(client: TestClient, db_session):
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
    response = client.get(f"/api/v1/metrics/run/{run.id}/comparison/summary")
    assert response.status_code == 409


def test_run_comparison_summary_groups_characteristics_and_marks_winner(client: TestClient, db_session):
    vertical = Vertical(name="V2", description=None)
    db_session.add(vertical)
    db_session.commit()
    db_session.refresh(vertical)
    primary = Brand(vertical_id=vertical.id, display_name="A", original_name="A", translated_name=None, aliases={"zh": [], "en": []})
    competitor = Brand(vertical_id=vertical.id, display_name="B", original_name="B", translated_name=None, aliases={"zh": [], "en": []})
    db_session.add_all([primary, competitor])
    db_session.commit()
    for obj in [primary, competitor]:
        db_session.refresh(obj)
    product_a = Product(vertical_id=vertical.id, brand_id=primary.id, display_name="P1", original_name="P1", translated_name=None)
    product_b = Product(vertical_id=vertical.id, brand_id=competitor.id, display_name="P2", original_name="P2", translated_name=None)
    db_session.add_all([product_a, product_b])
    db_session.commit()
    for obj in [product_a, product_b]:
        db_session.refresh(obj)
    run = Run(vertical_id=vertical.id, provider="qwen", model_name="qwen2.5:7b-instruct-q4_0", status=RunStatus.COMPLETED, run_time=datetime.utcnow())
    db_session.add(run)
    db_session.commit()
    db_session.refresh(run)
    db_session.add(RunComparisonConfig(run_id=run.id, vertical_id=vertical.id, primary_brand_id=primary.id, enabled=True, status=ComparisonRunStatus.COMPLETED))
    db_session.commit()
    prompt = ComparisonPrompt(
        run_id=run.id,
        vertical_id=vertical.id,
        prompt_type=ComparisonPromptType.PRODUCT_VS_PRODUCT,
        source=ComparisonPromptSource.GENERATED,
        text_zh="比较 P1 和 P2 的油耗",
        text_en="Compare the fuel efficiency of P1 and P2",
        primary_brand_id=primary.id,
        competitor_brand_id=competitor.id,
        primary_product_id=product_a.id,
        competitor_product_id=product_b.id,
        aspects=["油耗"],
    )
    db_session.add(prompt)
    db_session.commit()
    db_session.refresh(prompt)
    answer = ComparisonAnswer(
        run_id=run.id,
        comparison_prompt_id=prompt.id,
        provider=run.provider,
        model_name=run.model_name,
        raw_answer_zh="P1 更省油，P2 更耗油",
        raw_answer_en="P1 is more fuel-efficient; P2 consumes more fuel.",
    )
    db_session.add(answer)
    db_session.commit()
    db_session.refresh(answer)
    db_session.add_all([
        ComparisonSentimentObservation(
            run_id=run.id,
            comparison_answer_id=answer.id,
            entity_type=EntityType.PRODUCT,
            entity_id=product_a.id,
            entity_role=ComparisonEntityRole.PRIMARY,
            sentiment=Sentiment.POSITIVE,
            snippet_zh="P1 更省油",
            snippet_en="P1 is more fuel-efficient",
        ),
        ComparisonSentimentObservation(
            run_id=run.id,
            comparison_answer_id=answer.id,
            entity_type=EntityType.PRODUCT,
            entity_id=product_b.id,
            entity_role=ComparisonEntityRole.COMPETITOR,
            sentiment=Sentiment.NEGATIVE,
            snippet_zh="P2 更耗油",
            snippet_en="P2 consumes more fuel",
        ),
        ComparisonSentimentObservation(
            run_id=run.id,
            comparison_answer_id=answer.id,
            entity_type=EntityType.BRAND,
            entity_id=primary.id,
            entity_role=ComparisonEntityRole.PRIMARY,
            sentiment=Sentiment.POSITIVE,
            snippet_zh="P1 更省油",
            snippet_en="P1 is more fuel-efficient",
        ),
        ComparisonSentimentObservation(
            run_id=run.id,
            comparison_answer_id=answer.id,
            entity_type=EntityType.BRAND,
            entity_id=competitor.id,
            entity_role=ComparisonEntityRole.COMPETITOR,
            sentiment=Sentiment.NEGATIVE,
            snippet_zh="P2 更耗油",
            snippet_en="P2 consumes more fuel",
        ),
    ])
    db_session.commit()
    response = client.get(f"/api/v1/metrics/run/{run.id}/comparison/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["run_id"] == run.id
    assert data["characteristics"][0]["characteristic_zh"] == "油耗"
    assert data["characteristics"][0]["primary_wins"] == 1
    assert data["prompts"] == []
    detailed = client.get(f"/api/v1/metrics/run/{run.id}/comparison/summary?include_prompt_details=true")
    assert detailed.status_code == 200
    details = detailed.json()
    assert details["prompts"][0]["winner_role"] == "primary"
    assert details["prompts"][0]["winner_product_id"] == product_a.id
