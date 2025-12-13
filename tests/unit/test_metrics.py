"""Unit tests for metrics API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Brand, BrandMention, DailyMetrics, LLMAnswer, Prompt, Run, Vertical
from models.domain import PromptLanguage, RunStatus, Sentiment


@pytest.fixture
def setup_test_data(db_session: Session):
    vertical = Vertical(name="SUV Cars", description="Test vertical")
    db_session.add(vertical)
    db_session.flush()

    brand1 = Brand(
        vertical_id=vertical.id,
        display_name="VW",
        aliases={"zh": ["大众"], "en": []},
    )
    brand2 = Brand(
        vertical_id=vertical.id,
        display_name="Toyota",
        aliases={"zh": ["丰田"], "en": []},
    )
    db_session.add_all([brand1, brand2])
    db_session.flush()

    prompt1 = Prompt(
        vertical_id=vertical.id,
        text_en="Best SUV?",
        text_zh="最好的SUV?",
        language_original=PromptLanguage.EN,
    )
    prompt2 = Prompt(
        vertical_id=vertical.id,
        text_en="Top SUVs",
        text_zh="顶级SUV",
        language_original=PromptLanguage.EN,
    )
    db_session.add_all([prompt1, prompt2])
    db_session.flush()

    run = Run(
        vertical_id=vertical.id,
        model_name="qwen",
        status=RunStatus.COMPLETED,
    )
    db_session.add(run)
    db_session.flush()

    answer1 = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt1.id,
        raw_answer_zh="大众是最好的",
        raw_answer_en="VW is the best",
    )
    answer2 = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt2.id,
        raw_answer_zh="丰田很好",
        raw_answer_en="Toyota is good",
    )
    db_session.add_all([answer1, answer2])
    db_session.flush()

    mention1 = BrandMention(
        llm_answer_id=answer1.id,
        brand_id=brand1.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={"zh": ["大众是最好的"], "en": ["VW is the best"]},
    )
    mention2 = BrandMention(
        llm_answer_id=answer1.id,
        brand_id=brand2.id,
        mentioned=False,
        rank=None,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={},
    )
    mention3 = BrandMention(
        llm_answer_id=answer2.id,
        brand_id=brand1.id,
        mentioned=False,
        rank=None,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={},
    )
    mention4 = BrandMention(
        llm_answer_id=answer2.id,
        brand_id=brand2.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={"zh": ["丰田很好"], "en": ["Toyota is good"]},
    )
    db_session.add_all([mention1, mention2, mention3, mention4])
    db_session.commit()

    return {
        "vertical_id": vertical.id,
        "brand1_id": brand1.id,
        "brand2_id": brand2.id,
        "run_id": run.id,
    }


def test_get_latest_metrics(client: TestClient, setup_test_data):
    vertical_id = setup_test_data["vertical_id"]

    response = client.get(
        f"/api/v1/metrics/latest?vertical_id={vertical_id}&model_name=qwen"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["vertical_id"] == vertical_id
    assert data["vertical_name"] == "SUV Cars"
    assert data["model_name"] == "qwen"
    assert len(data["brands"]) == 2

    vw_metrics = next(b for b in data["brands"] if b["brand_name"] == "VW")
    assert vw_metrics["mention_rate"] == 0.5
    assert vw_metrics["avg_rank"] == 1.0
    assert vw_metrics["sentiment_positive"] == 1.0

    toyota_metrics = next(b for b in data["brands"] if b["brand_name"] == "Toyota")
    assert toyota_metrics["mention_rate"] == 0.5
    assert toyota_metrics["avg_rank"] == 1.0
    assert toyota_metrics["sentiment_positive"] == 1.0


def test_get_latest_metrics_no_data(client: TestClient):
    response = client.get("/api/v1/metrics/latest?vertical_id=999&model_name=qwen")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_get_latest_metrics_no_runs(client: TestClient):
    vertical_response = client.post(
        "/api/v1/verticals",
        json={"name": "Empty Vertical"},
    )
    vertical_id = vertical_response.json()["id"]

    response = client.get(
        f"/api/v1/metrics/latest?vertical_id={vertical_id}&model_name=qwen"
    )

    assert response.status_code == 404
    assert "No runs found" in response.json()["detail"]


def test_get_daily_metrics_empty(client: TestClient, setup_test_data):
    vertical_id = setup_test_data["vertical_id"]
    brand_id = setup_test_data["brand1_id"]

    response = client.get(
        f"/api/v1/metrics/daily?vertical_id={vertical_id}&brand_id={brand_id}&model_name=qwen"
    )

    assert response.status_code == 200
    data = response.json()
    assert data["vertical_id"] == vertical_id
    assert data["brand_id"] == brand_id
    assert data["model_name"] == "qwen"
    assert data["data"] == []


def test_get_daily_metrics_with_data(client: TestClient, db_session: Session, setup_test_data):
    vertical_id = setup_test_data["vertical_id"]
    brand_id = setup_test_data["brand1_id"]

    prompt = db_session.query(Prompt).filter(Prompt.vertical_id == vertical_id).first()

    metric = DailyMetrics(
        date=db_session.query(Run).first().run_time,
        vertical_id=vertical_id,
        model_name="qwen",
        prompt_id=prompt.id,
        brand_id=brand_id,
        mention_rate=0.75,
        avg_rank=2.0,
        sentiment_pos=0.6,
        sentiment_neu=0.3,
        sentiment_neg=0.1,
    )
    db_session.add(metric)
    db_session.commit()

    response = client.get(
        f"/api/v1/metrics/daily?vertical_id={vertical_id}&brand_id={brand_id}&model_name=qwen"
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1
    assert data["data"][0]["mention_rate"] == 0.75
    assert data["data"][0]["avg_rank"] == 2.0
    assert data["data"][0]["sentiment_positive"] == 0.6


def test_get_daily_metrics_brand_not_in_vertical(
    client: TestClient, db_session: Session, setup_test_data
):
    other_vertical = Vertical(name="Other", description="Other vertical")
    db_session.add(other_vertical)
    db_session.flush()

    other_brand = Brand(
        vertical_id=other_vertical.id,
        display_name="Ford",
        aliases={"zh": [], "en": []},
    )
    db_session.add(other_brand)
    db_session.commit()

    response = client.get(
        "/api/v1/metrics/daily",
        params={
            "vertical_id": setup_test_data["vertical_id"],
            "brand_id": other_brand.id,
            "model_name": "qwen",
        },
    )

    assert response.status_code == 404
    assert "Brand" in response.json()["detail"]


def test_get_daily_metrics_invalid_date_range(
    client: TestClient, setup_test_data
):
    vertical_id = setup_test_data["vertical_id"]
    brand_id = setup_test_data["brand1_id"]

    response = client.get(
        "/api/v1/metrics/daily",
        params={
            "vertical_id": vertical_id,
            "brand_id": brand_id,
            "model_name": "qwen",
            "start_date": "2024-05-02T00:00:00",
            "end_date": "2024-05-01T00:00:00",
        },
    )

    assert response.status_code == 400
    assert "start_date" in response.json()["detail"]
