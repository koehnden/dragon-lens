"""End-to-end integration tests for complete workflows."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Brand, BrandMention, LLMAnswer, Prompt, Run
from models.domain import RunStatus, Sentiment


def test_complete_tracking_workflow(client: TestClient, db_session: Session):
    """Test complete workflow from vertical creation to metrics retrieval."""
    # Step 1: Create a vertical directly
    vertical_response = client.post(
        "/api/v1/verticals",
        json={
            "name": "Electric Vehicles",
            "description": "Battery-powered vehicles",
        },
    )
    assert vertical_response.status_code == 201
    vertical_id = vertical_response.json()["id"]

    # Step 2: Verify vertical exists
    get_vertical = client.get(f"/api/v1/verticals/{vertical_id}")
    assert get_vertical.status_code == 200
    assert get_vertical.json()["name"] == "Electric Vehicles"

    # Step 3: Create a tracking job for this vertical
    job_response = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Electric Vehicles",
            "brands": [
                {
                    "display_name": "Tesla",
                    "aliases": {"zh": ["特斯拉"], "en": ["TSLA"]},
                },
                {
                    "display_name": "BYD",
                    "aliases": {"zh": ["比亚迪"], "en": []},
                },
                {
                    "display_name": "NIO",
                    "aliases": {"zh": ["蔚来"], "en": []},
                },
            ],
            "prompts": [
                {"text_en": "Best electric car?", "text_zh": "最好的电动车?", "language_original": "en"},
                {
                    "text_en": "Recommend an EV",
                    "text_zh": "推荐一款电动车",
                    "language_original": "en",
                },
            ],
            "model_name": "qwen",
        },
    )
    assert job_response.status_code == 201
    run_id = job_response.json()["run_id"]

    # Step 4: Verify run was created
    run_response = client.get(f"/api/v1/tracking/runs/{run_id}")
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "pending"

    # Step 5: List all runs for this vertical
    runs_list = client.get(f"/api/v1/tracking/runs?vertical_id={vertical_id}")
    assert runs_list.status_code == 200
    assert len(runs_list.json()) == 1

    # Step 6: Simulate processing by adding answers and mentions
    run = db_session.query(Run).filter(Run.id == run_id).first()
    prompts = db_session.query(Prompt).filter(Prompt.vertical_id == vertical_id).all()
    brands = db_session.query(Brand).filter(Brand.vertical_id == vertical_id).all()

    # Create answers for each prompt
    for prompt in prompts:
        answer = LLMAnswer(
            run_id=run_id,
            prompt_id=prompt.id,
            raw_answer_zh="特斯拉是最好的选择",
            raw_answer_en="Tesla is the best choice",
        )
        db_session.add(answer)
        db_session.flush()

        # Add mentions for each brand
        for idx, brand in enumerate(brands):
            if brand.display_name == "Tesla":
                mention = BrandMention(
                    llm_answer_id=answer.id,
                    brand_id=brand.id,
                    mentioned=True,
                    rank=1,
                    sentiment=Sentiment.POSITIVE,
                    evidence_snippets={"zh": ["特斯拉是最好的"], "en": ["Tesla is the best"]},
                )
            else:
                mention = BrandMention(
                    llm_answer_id=answer.id,
                    brand_id=brand.id,
                    mentioned=False,
                    rank=None,
                    sentiment=Sentiment.NEUTRAL,
                    evidence_snippets={},
                )
            db_session.add(mention)

    # Mark run as completed
    run.status = RunStatus.COMPLETED
    db_session.commit()

    # Step 7: Verify run status updated
    updated_run = client.get(f"/api/v1/tracking/runs/{run_id}")
    assert updated_run.json()["status"] == "completed"

    # Step 8: Get latest metrics
    metrics_response = client.get(
        f"/api/v1/metrics/latest?vertical_id={vertical_id}&model_name=qwen"
    )
    assert metrics_response.status_code == 200

    metrics_data = metrics_response.json()
    assert metrics_data["vertical_name"] == "Electric Vehicles"
    assert len(metrics_data["brands"]) == 3

    # Step 9: Verify Tesla has highest metrics
    tesla_metrics = next(b for b in metrics_data["brands"] if b["brand_name"] == "Tesla")
    assert tesla_metrics["mention_rate"] == 1.0  # Mentioned in all prompts
    assert tesla_metrics["avg_rank"] == 1.0  # Always ranked first
    assert tesla_metrics["sentiment_positive"] == 1.0  # All positive sentiment

    # Step 10: Verify other brands have zero metrics
    byd_metrics = next(b for b in metrics_data["brands"] if b["brand_name"] == "BYD")
    assert byd_metrics["mention_rate"] == 0.0

    nio_metrics = next(b for b in metrics_data["brands"] if b["brand_name"] == "NIO")
    assert nio_metrics["mention_rate"] == 0.0


def test_multiple_verticals_isolation_workflow(client: TestClient):
    """Test that multiple verticals maintain data isolation."""
    # Create two different verticals with tracking jobs
    job1 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Smartphones",
            "brands": [{"display_name": "Apple"}, {"display_name": "Samsung"}],
            "prompts": [{"text_en": "Best phone?", "language_original": "en"}],
            "model_name": "qwen",
        },
    )

    job2 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Laptops",
            "brands": [{"display_name": "Dell"}, {"display_name": "HP"}],
            "prompts": [{"text_en": "Best laptop?", "language_original": "en"}],
            "model_name": "qwen",
        },
    )

    vertical1_id = job1.json()["vertical_id"]
    vertical2_id = job2.json()["vertical_id"]

    assert vertical1_id != vertical2_id

    # Verify runs are associated with correct verticals
    v1_runs = client.get(f"/api/v1/tracking/runs?vertical_id={vertical1_id}")
    assert len(v1_runs.json()) == 1
    assert v1_runs.json()[0]["vertical_id"] == vertical1_id

    v2_runs = client.get(f"/api/v1/tracking/runs?vertical_id={vertical2_id}")
    assert len(v2_runs.json()) == 1
    assert v2_runs.json()[0]["vertical_id"] == vertical2_id


def test_multi_model_workflow(client: TestClient, db_session: Session):
    """Test workflow with multiple models for same vertical."""
    # Create a vertical with a tracking job
    job1 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Gaming Consoles",
            "brands": [{"display_name": "PlayStation"}, {"display_name": "Xbox"}],
            "prompts": [{"text_en": "Best console?", "language_original": "en"}],
            "model_name": "qwen",
        },
    )

    vertical_id = job1.json()["vertical_id"]
    run1_id = job1.json()["run_id"]

    # Create another job with different model
    job2 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Gaming Consoles",
            "brands": [{"display_name": "Nintendo"}],  # New brand
            "prompts": [{"text_en": "Top console?", "language_original": "en"}],
            "model_name": "deepseek",
        },
    )

    run2_id = job2.json()["run_id"]

    # Both should use same vertical
    assert job1.json()["vertical_id"] == job2.json()["vertical_id"]

    # But different runs
    assert run1_id != run2_id

    # Verify filtering by model works
    qwen_runs = client.get(f"/api/v1/tracking/runs?vertical_id={vertical_id}&model_name=qwen")
    assert len(qwen_runs.json()) == 1
    assert qwen_runs.json()[0]["id"] == run1_id

    deepseek_runs = client.get(
        f"/api/v1/tracking/runs?vertical_id={vertical_id}&model_name=deepseek"
    )
    assert len(deepseek_runs.json()) == 1
    assert deepseek_runs.json()[0]["id"] == run2_id


def test_incremental_brand_addition(client: TestClient, db_session: Session):
    """Test adding more brands to existing vertical over multiple jobs."""
    # Job 1: Initial brands
    job1 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Streaming Services",
            "brands": [{"display_name": "Netflix"}, {"display_name": "Disney+"}],
            "prompts": [{"text_en": "Best streaming?", "language_original": "en"}],
        },
    )

    vertical_id = job1.json()["vertical_id"]

    # Verify 2 brands exist
    brands1 = db_session.query(Brand).filter(Brand.vertical_id == vertical_id).all()
    assert len(brands1) == 2

    # Job 2: Add more brands
    job2 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Streaming Services",
            "brands": [{"display_name": "HBO Max"}, {"display_name": "Prime Video"}],
            "prompts": [{"text_en": "Top streaming?", "language_original": "en"}],
        },
    )

    # Verify all 4 brands now exist
    brands2 = db_session.query(Brand).filter(Brand.vertical_id == vertical_id).all()
    assert len(brands2) == 4

    brand_names = {b.display_name for b in brands2}
    assert brand_names == {"Netflix", "Disney+", "HBO Max", "Prime Video"}


def test_error_handling_workflow(client: TestClient):
    """Test error handling across the workflow."""
    # Try to get metrics for non-existent vertical
    metrics = client.get("/api/v1/metrics/latest?vertical_id=99999&model_name=qwen")
    assert metrics.status_code == 404

    # Try to get non-existent run
    run = client.get("/api/v1/tracking/runs/99999")
    assert run.status_code == 404

    # Try to get non-existent vertical
    vertical = client.get("/api/v1/verticals/99999")
    assert vertical.status_code == 404

    # Try to create duplicate vertical
    client.post("/api/v1/verticals", json={"name": "Duplicate Test"})
    duplicate = client.post("/api/v1/verticals", json={"name": "Duplicate Test"})
    assert duplicate.status_code == 400


def test_bilingual_prompt_workflow(client: TestClient, db_session: Session):
    """Test workflow with both English and Chinese prompts."""
    job = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Coffee Brands",
            "brands": [{"display_name": "Starbucks"}, {"display_name": "Luckin Coffee"}],
            "prompts": [
                # English prompt
                {"text_en": "Best coffee chain?", "text_zh": None, "language_original": "en"},
                # Chinese prompt
                {"text_en": None, "text_zh": "最好的咖啡店?", "language_original": "zh"},
                # Bilingual prompt
                {
                    "text_en": "Top coffee brand",
                    "text_zh": "顶级咖啡品牌",
                    "language_original": "en",
                },
            ],
        },
    )

    vertical_id = job.json()["vertical_id"]

    # Verify all prompts were created correctly
    prompts = db_session.query(Prompt).filter(Prompt.vertical_id == vertical_id).all()
    assert len(prompts) == 3

    # Check language flags
    en_only = [p for p in prompts if p.text_en and not p.text_zh]
    zh_only = [p for p in prompts if p.text_zh and not p.text_en]
    bilingual = [p for p in prompts if p.text_en and p.text_zh]

    assert len(en_only) == 1
    assert len(zh_only) == 1
    assert len(bilingual) == 1
