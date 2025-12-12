"""Integration tests for tracking API endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Brand, Prompt, Run, Vertical


def test_tracking_job_creates_full_structure(client: TestClient, db_session: Session):
    """Test that tracking job creates all related entities."""
    response = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Luxury SUVs",
            "vertical_description": "Premium sport utility vehicles",
            "brands": [
                {
                    "display_name": "Mercedes-Benz",
                    "aliases": {"zh": ["奔驰"], "en": ["Mercedes", "Merc"]},
                },
                {
                    "display_name": "BMW",
                    "aliases": {"zh": ["宝马"], "en": ["Bayerische Motoren Werke"]},
                },
            ],
            "prompts": [
                {"text_en": "Best luxury SUVs?", "text_zh": None, "language_original": "en"},
                {"text_en": None, "text_zh": "最好的豪华SUV?", "language_original": "zh"},
                {"text_en": "Top SUV brands", "text_zh": "顶级SUV品牌", "language_original": "en"},
            ],
            "model_name": "qwen",
        },
    )

    assert response.status_code == 201
    data = response.json()

    # Check response
    assert data["run_id"] > 0
    assert data["vertical_id"] > 0
    assert data["model_name"] == "qwen"
    assert data["status"] == "pending"

    # Verify vertical was created
    vertical = db_session.query(Vertical).filter(Vertical.id == data["vertical_id"]).first()
    assert vertical is not None
    assert vertical.name == "Luxury SUVs"
    assert vertical.description == "Premium sport utility vehicles"

    # Verify brands were created
    brands = db_session.query(Brand).filter(Brand.vertical_id == data["vertical_id"]).all()
    assert len(brands) == 2
    brand_names = {b.display_name for b in brands}
    assert "Mercedes-Benz" in brand_names
    assert "BMW" in brand_names

    # Check aliases
    merc = next(b for b in brands if b.display_name == "Mercedes-Benz")
    assert "奔驰" in merc.aliases["zh"]
    assert "Mercedes" in merc.aliases["en"]

    # Verify prompts were created
    prompts = db_session.query(Prompt).filter(Prompt.vertical_id == data["vertical_id"]).all()
    assert len(prompts) == 3

    # Verify run was created
    run = db_session.query(Run).filter(Run.id == data["run_id"]).first()
    assert run is not None
    assert run.vertical_id == data["vertical_id"]
    assert run.model_name == "qwen"
    assert run.status.value == "pending"


def test_tracking_job_reuses_existing_vertical(client: TestClient, db_session: Session):
    """Test that tracking job reuses existing vertical."""
    # Create first job
    job1 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Smartphones",
            "brands": [{"display_name": "Apple"}],
            "prompts": [{"text_en": "Test 1", "language_original": "en"}],
        },
    )
    vertical_id_1 = job1.json()["vertical_id"]

    # Count verticals before second job
    verticals_before = db_session.query(Vertical).count()

    # Create second job with same vertical name
    job2 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Smartphones",
            "brands": [{"display_name": "Samsung"}],
            "prompts": [{"text_en": "Test 2", "language_original": "en"}],
        },
    )
    vertical_id_2 = job2.json()["vertical_id"]

    # Count verticals after second job
    verticals_after = db_session.query(Vertical).count()

    # Should reuse the same vertical
    assert vertical_id_1 == vertical_id_2
    assert verticals_before == verticals_after

    # But should create new brands
    brands = db_session.query(Brand).filter(Brand.vertical_id == vertical_id_1).all()
    brand_names = {b.display_name for b in brands}
    assert "Apple" in brand_names
    assert "Samsung" in brand_names


def test_tracking_job_with_chinese_prompts(client: TestClient, db_session: Session):
    """Test tracking job with Chinese-only prompts."""
    response = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "电动车",
            "brands": [{"display_name": "特斯拉"}],
            "prompts": [
                {"text_en": None, "text_zh": "最好的电动车是什么?", "language_original": "zh"},
                {"text_en": None, "text_zh": "推荐一款电动SUV", "language_original": "zh"},
            ],
            "model_name": "qwen",
        },
    )

    assert response.status_code == 201
    data = response.json()

    # Verify prompts stored correctly
    prompts = (
        db_session.query(Prompt)
        .filter(Prompt.vertical_id == data["vertical_id"])
        .all()
    )
    assert len(prompts) == 2
    assert all(p.text_zh is not None for p in prompts)
    assert all(p.language_original.value == "zh" for p in prompts)


def test_list_runs_filtering(client: TestClient):
    """Test run listing with various filters."""
    # Create jobs for different verticals and models
    job1 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Cars",
            "brands": [{"display_name": "Toyota"}],
            "prompts": [{"text_en": "Test", "language_original": "en"}],
            "model_name": "qwen",
        },
    )

    job2 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Cars",
            "brands": [{"display_name": "Honda"}],
            "prompts": [{"text_en": "Test", "language_original": "en"}],
            "model_name": "deepseek",
        },
    )

    job3 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Phones",
            "brands": [{"display_name": "Apple"}],
            "prompts": [{"text_en": "Test", "language_original": "en"}],
            "model_name": "qwen",
        },
    )

    # Test filter by vertical
    cars_runs = client.get(f"/api/v1/tracking/runs?vertical_id={job1.json()['vertical_id']}")
    assert len(cars_runs.json()) == 2

    # Test filter by model
    qwen_runs = client.get("/api/v1/tracking/runs?model_name=qwen")
    assert len(qwen_runs.json()) == 2

    # Test combined filters
    cars_qwen = client.get(
        f"/api/v1/tracking/runs?vertical_id={job1.json()['vertical_id']}&model_name=qwen"
    )
    assert len(cars_qwen.json()) == 1


def test_run_ordering(client: TestClient):
    """Test that runs are returned in an ordered manner."""
    # Create multiple jobs
    jobs = []
    for i in range(3):
        job = client.post(
            "/api/v1/tracking/jobs",
            json={
                "vertical_name": f"Test {i}",
                "brands": [{"display_name": "Brand"}],
                "prompts": [{"text_en": "Test", "language_original": "en"}],
            },
        )
        jobs.append(job.json()["run_id"])

    # List all runs
    response = client.get("/api/v1/tracking/runs")
    runs = response.json()
    run_ids = [r["id"] for r in runs]

    # All jobs should be present
    assert len(run_ids) == 3
    assert set(run_ids) == set(jobs)

    # Verify that run_time field exists and is consistent
    for run in runs:
        assert "run_time" in run
        assert run["run_time"] is not None

    # Runs should be ordered by time descending
    # Note: When runs have the same timestamp (which happens in tests),
    # the exact order may vary, but the query is correct (order_by run_time desc)
    run_times = [r["run_time"] for r in runs]
    assert run_times == sorted(run_times, reverse=True)


def test_get_run_details(client: TestClient):
    """Test retrieving detailed run information."""
    # Create a job
    job = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Test Vertical",
            "brands": [{"display_name": "Test Brand"}],
            "prompts": [{"text_en": "Test prompt", "language_original": "en"}],
            "model_name": "qwen",
        },
    )
    run_id = job.json()["run_id"]

    # Get run details
    response = client.get(f"/api/v1/tracking/runs/{run_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == run_id
    assert data["model_name"] == "qwen"
    assert data["status"] == "pending"
    assert data["run_time"] is not None
    assert data["completed_at"] is None
    assert data["error_message"] is None


def test_tracking_job_minimal_data(client: TestClient):
    """Test tracking job with minimal required data."""
    response = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Minimal Test",
            "brands": [{"display_name": "Brand A"}],
            "prompts": [{"text_en": "Question?", "language_original": "en"}],
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["model_name"] == "qwen"  # Default model
    assert data["status"] == "pending"
