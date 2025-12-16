"""Integration tests for metrics API endpoints."""

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Brand, BrandMention, DailyMetrics, LLMAnswer, Prompt, Run, RunMetrics, Vertical
from models.domain import PromptLanguage, RunStatus, Sentiment
from services.metrics_service import calculate_and_save_metrics


@pytest.fixture
def complete_test_data(db_session: Session):
    """Create a complete test dataset with vertical, brands, prompts, runs, answers, and mentions."""
    # Create vertical
    vertical = Vertical(name="Luxury Cars", description="Premium vehicles")
    db_session.add(vertical)
    db_session.flush()

    # Create brands
    brand1 = Brand(
        vertical_id=vertical.id,
        display_name="Mercedes-Benz",
        original_name="Mercedes-Benz",
        translated_name="Mercedes-Benz",
        aliases={"zh": ["奔驰"], "en": ["Mercedes"]},
    )
    brand2 = Brand(
        vertical_id=vertical.id,
        display_name="BMW",
        original_name="BMW",
        translated_name="BMW",
        aliases={"zh": ["宝马"], "en": []},
    )
    brand3 = Brand(
        vertical_id=vertical.id,
        display_name="Audi",
        original_name="Audi",
        translated_name="Audi",
        aliases={"zh": ["奥迪"], "en": []},
    )
    db_session.add_all([brand1, brand2, brand3])
    db_session.flush()

    # Create prompts
    prompt1 = Prompt(
        vertical_id=vertical.id,
        text_en="Best luxury car?",
        text_zh="最好的豪华车?",
        language_original=PromptLanguage.EN,
    )
    prompt2 = Prompt(
        vertical_id=vertical.id,
        text_en="Recommend a luxury sedan",
        text_zh="推荐豪华轿车",
        language_original=PromptLanguage.EN,
    )
    prompt3 = Prompt(
        vertical_id=vertical.id,
        text_en="Top luxury brands",
        text_zh="顶级豪华品牌",
        language_original=PromptLanguage.EN,
    )
    db_session.add_all([prompt1, prompt2, prompt3])
    db_session.flush()

    # Create run
    run = Run(
        vertical_id=vertical.id,
        model_name="qwen",
        status=RunStatus.COMPLETED,
    )
    db_session.add(run)
    db_session.flush()

    # Create answers and mentions
    # Answer 1: Mercedes mentioned positively at rank 1
    answer1 = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt1.id,
        raw_answer_zh="奔驰是最好的选择",
        raw_answer_en="Mercedes is the best choice",
    )
    db_session.add(answer1)
    db_session.flush()

    mention1_1 = BrandMention(
        llm_answer_id=answer1.id,
        brand_id=brand1.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={"zh": ["奔驰是最好的"], "en": ["Mercedes is the best"]},
    )
    mention1_2 = BrandMention(
        llm_answer_id=answer1.id,
        brand_id=brand2.id,
        mentioned=False,
        rank=None,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={},
    )
    mention1_3 = BrandMention(
        llm_answer_id=answer1.id,
        brand_id=brand3.id,
        mentioned=False,
        rank=None,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={},
    )
    db_session.add_all([mention1_1, mention1_2, mention1_3])

    # Answer 2: BMW mentioned positively at rank 1, Mercedes at rank 2
    answer2 = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt2.id,
        raw_answer_zh="我推荐宝马，其次是奔驰",
        raw_answer_en="I recommend BMW, followed by Mercedes",
    )
    db_session.add(answer2)
    db_session.flush()

    mention2_1 = BrandMention(
        llm_answer_id=answer2.id,
        brand_id=brand1.id,
        mentioned=True,
        rank=2,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={"zh": ["其次是奔驰"], "en": ["followed by Mercedes"]},
    )
    mention2_2 = BrandMention(
        llm_answer_id=answer2.id,
        brand_id=brand2.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={"zh": ["推荐宝马"], "en": ["recommend BMW"]},
    )
    mention2_3 = BrandMention(
        llm_answer_id=answer2.id,
        brand_id=brand3.id,
        mentioned=False,
        rank=None,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={},
    )
    db_session.add_all([mention2_1, mention2_2, mention2_3])

    # Answer 3: All three mentioned, mixed sentiment
    answer3 = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt3.id,
        raw_answer_zh="宝马、奔驰和奥迪都是顶级品牌，但奥迪稍逊一筹",
        raw_answer_en="BMW, Mercedes and Audi are top brands, but Audi is slightly inferior",
    )
    db_session.add(answer3)
    db_session.flush()

    mention3_1 = BrandMention(
        llm_answer_id=answer3.id,
        brand_id=brand1.id,
        mentioned=True,
        rank=2,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={"zh": ["奔驰"], "en": ["Mercedes"]},
    )
    mention3_2 = BrandMention(
        llm_answer_id=answer3.id,
        brand_id=brand2.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.POSITIVE,
        evidence_snippets={"zh": ["宝马"], "en": ["BMW"]},
    )
    mention3_3 = BrandMention(
        llm_answer_id=answer3.id,
        brand_id=brand3.id,
        mentioned=True,
        rank=3,
        sentiment=Sentiment.NEGATIVE,
        evidence_snippets={"zh": ["奥迪稍逊一筹"], "en": ["Audi is slightly inferior"]},
    )
    db_session.add_all([mention3_1, mention3_2, mention3_3])

    db_session.commit()

    return {
        "vertical_id": vertical.id,
        "brand1_id": brand1.id,
        "brand2_id": brand2.id,
        "brand3_id": brand3.id,
        "run_id": run.id,
    }


def test_latest_metrics_calculation(client: TestClient, complete_test_data):
    vertical_id = complete_test_data["vertical_id"]

    response = client.get(f"/api/v1/metrics/latest?vertical_id={vertical_id}&model_name=qwen")

    assert response.status_code == 200
    data = response.json()

    assert data["vertical_id"] == vertical_id
    assert data["vertical_name"] == "Luxury Cars"
    assert data["model_name"] == "qwen"
    assert len(data["brands"]) == 3

    merc = next(b for b in data["brands"] if b["brand_name"] == "Mercedes-Benz")
    assert merc["mention_rate"] == pytest.approx(1.0, rel=1e-2)
    assert merc["share_of_voice"] == pytest.approx(0.47, rel=1e-2)
    assert merc["top_spot_share"] == pytest.approx(1 / 3, rel=1e-2)
    assert merc["sentiment_index"] == pytest.approx(1.0, rel=1e-2)
    assert merc["dragon_lens_visibility"] == pytest.approx(0.55, rel=1e-2)

    bmw = next(b for b in data["brands"] if b["brand_name"] == "BMW")
    assert bmw["mention_rate"] == pytest.approx(2 / 3, rel=1e-2)
    assert bmw["share_of_voice"] == pytest.approx(0.42, rel=1e-2)
    assert bmw["top_spot_share"] == pytest.approx(2 / 3, rel=1e-2)
    assert bmw["sentiment_index"] == pytest.approx(1.0, rel=1e-2)
    assert bmw["dragon_lens_visibility"] == pytest.approx(0.59, rel=1e-2)

    audi = next(b for b in data["brands"] if b["brand_name"] == "Audi")
    assert audi["mention_rate"] == pytest.approx(1 / 3, rel=1e-2)
    assert audi["share_of_voice"] == pytest.approx(0.1, rel=1e-2)
    assert audi["top_spot_share"] == 0.0
    assert audi["sentiment_index"] == 0.0
    assert audi["dragon_lens_visibility"] == pytest.approx(0.06, rel=1e-2)


def test_latest_metrics_with_multiple_runs(client: TestClient, db_session: Session, complete_test_data):
    """Test that only the latest run is used for metrics."""
    vertical_id = complete_test_data["vertical_id"]

    # Create an older run (by manipulating the timestamp)
    old_run = Run(
        vertical_id=vertical_id,
        model_name="qwen",
        status=RunStatus.COMPLETED,
    )
    db_session.add(old_run)
    db_session.commit()

    # Get metrics - should use the most recent run
    response = client.get(f"/api/v1/metrics/latest?vertical_id={vertical_id}&model_name=qwen")

    assert response.status_code == 200
    data = response.json()

    # The latest run should have data (from complete_test_data fixture)
    # If it used the old run (which has no answers), metrics would be 0
    merc = next(b for b in data["brands"] if b["brand_name"] == "Mercedes-Benz")
    assert merc["mention_rate"] > 0


def test_latest_metrics_nonexistent_vertical(client: TestClient):
    """Test metrics endpoint with non-existent vertical."""
    response = client.get("/api/v1/metrics/latest?vertical_id=99999&model_name=qwen")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_latest_metrics_no_runs(client: TestClient):
    """Test metrics when vertical exists but has no runs."""
    # Create vertical without any runs
    vertical = client.post("/api/v1/verticals", json={"name": "Empty Vertical"})
    vertical_id = vertical.json()["id"]

    response = client.get(f"/api/v1/metrics/latest?vertical_id={vertical_id}&model_name=qwen")

    assert response.status_code == 404
    assert "no runs found" in response.json()["detail"].lower()


def test_daily_metrics_with_data(client: TestClient, db_session: Session, complete_test_data):
    vertical_id = complete_test_data["vertical_id"]
    brand_id = complete_test_data["brand1_id"]

    run = db_session.query(Run).filter(Run.id == complete_test_data["run_id"]).first()
    prompt = db_session.query(Prompt).filter(Prompt.vertical_id == vertical_id).first()

    base_date = datetime.now()
    for i in range(5):
        metric = DailyMetrics(
            date=base_date - timedelta(days=i),
            vertical_id=vertical_id,
            model_name="qwen",
            prompt_id=prompt.id,
            brand_id=brand_id,
            mention_rate=0.5 + i * 0.1,
            share_of_voice=0.3 + i * 0.05,
            top_spot_share=0.2 + i * 0.05,
            sentiment_index=0.6 - i * 0.05,
            dragon_lens_visibility=0.4 + i * 0.04,
        )
        db_session.add(metric)
    db_session.commit()

    # Get daily metrics
    response = client.get(
        f"/api/v1/metrics/daily?vertical_id={vertical_id}&brand_id={brand_id}&model_name=qwen"
    )

    assert response.status_code == 200
    data = response.json()

    assert data["vertical_id"] == vertical_id
    assert data["brand_id"] == brand_id
    assert data["model_name"] == "qwen"
    assert len(data["data"]) == 5

    dates = [d["date"] for d in data["data"]]
    assert dates == sorted(dates)


def test_daily_metrics_date_filtering(client: TestClient, db_session: Session, complete_test_data):
    vertical_id = complete_test_data["vertical_id"]
    brand_id = complete_test_data["brand1_id"]
    prompt = db_session.query(Prompt).filter(Prompt.vertical_id == vertical_id).first()

    base_date = datetime.now()
    for i in range(10):
        metric = DailyMetrics(
            date=base_date - timedelta(days=i),
            vertical_id=vertical_id,
            model_name="qwen",
            prompt_id=prompt.id,
            brand_id=brand_id,
            mention_rate=0.5,
            share_of_voice=0.4,
            top_spot_share=0.3,
            sentiment_index=0.6,
            dragon_lens_visibility=0.5,
        )
        db_session.add(metric)
    db_session.commit()

    # Filter to last 5 days
    start_date = (base_date - timedelta(days=4)).isoformat()
    response = client.get(
        f"/api/v1/metrics/daily?vertical_id={vertical_id}&brand_id={brand_id}"
        f"&model_name=qwen&start_date={start_date}"
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 5


def test_metrics_across_different_models(client: TestClient, db_session: Session, complete_test_data):
    vertical_id = complete_test_data["vertical_id"]

    run2 = Run(
        vertical_id=vertical_id,
        model_name="deepseek",
        status=RunStatus.COMPLETED,
    )
    db_session.add(run2)
    db_session.commit()

    qwen_metrics = client.get(
        f"/api/v1/metrics/latest?vertical_id={vertical_id}&model_name=qwen"
    )

    deepseek_metrics = client.get(
        f"/api/v1/metrics/latest?vertical_id={vertical_id}&model_name=deepseek"
    )

    assert qwen_metrics.status_code == 200
    assert deepseek_metrics.status_code == 200

    qwen_brands = qwen_metrics.json()["brands"]
    assert any(b["mention_rate"] > 0 for b in qwen_brands)

    deepseek_brands = deepseek_metrics.json()["brands"]
    assert all(b["mention_rate"] == 0 for b in deepseek_brands)


def test_calculate_and_save_metrics_service(db_session: Session, complete_test_data):
    run_id = complete_test_data["run_id"]

    calculate_and_save_metrics(db_session, run_id)

    run_metrics = db_session.query(RunMetrics).filter(RunMetrics.run_id == run_id).all()

    assert len(run_metrics) == 3

    merc_metrics = next(m for m in run_metrics if m.brand_id == complete_test_data["brand1_id"])
    assert merc_metrics.mention_rate == pytest.approx(1.0, rel=1e-2)
    assert merc_metrics.share_of_voice == pytest.approx(0.47, rel=1e-2)
    assert merc_metrics.top_spot_share == pytest.approx(1 / 3, rel=1e-2)
    assert merc_metrics.sentiment_index == pytest.approx(1.0, rel=1e-2)
    assert merc_metrics.dragon_lens_visibility > 0


def test_run_metrics_endpoint(client: TestClient, db_session: Session, complete_test_data):
    run_id = complete_test_data["run_id"]

    calculate_and_save_metrics(db_session, run_id)

    response = client.get(f"/api/v1/metrics/run/{run_id}")

    assert response.status_code == 200
    data = response.json()

    assert data["run_id"] == run_id
    assert data["vertical_name"] == "Luxury Cars"
    assert data["model_name"] == "qwen"
    assert len(data["metrics"]) == 3

    merc = next(m for m in data["metrics"] if m["brand_name"] == "Mercedes-Benz")
    assert merc["mention_rate"] == pytest.approx(1.0, rel=1e-2)
    assert merc["share_of_voice"] == pytest.approx(0.47, rel=1e-2)
    assert merc["dragon_lens_visibility"] > 0


def test_run_metrics_endpoint_nonexistent_run(client: TestClient):
    response = client.get("/api/v1/metrics/run/99999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_run_metrics_endpoint_no_metrics_calculated(client: TestClient, db_session: Session, complete_test_data):
    vertical_id = complete_test_data["vertical_id"]

    new_run = Run(
        vertical_id=vertical_id,
        model_name="qwen",
        status=RunStatus.COMPLETED,
    )
    db_session.add(new_run)
    db_session.commit()

    response = client.get(f"/api/v1/metrics/run/{new_run.id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data["metrics"]) == 0
