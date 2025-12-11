"""Unit tests for tracking API endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_create_tracking_job(client: TestClient):
    response = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "SUV Cars",
            "vertical_description": "Sport utility vehicles",
            "brands": [
                {"display_name": "Volkswagen", "aliases": {"zh": ["大众"], "en": ["VW"]}},
                {"display_name": "Toyota", "aliases": {"zh": ["丰田"], "en": []}},
            ],
            "prompts": [
                {"text_en": "Best SUV cars?", "text_zh": None, "language_original": "en"},
                {"text_en": None, "text_zh": "最好的SUV汽车？", "language_original": "zh"},
            ],
            "model_name": "qwen",
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert "run_id" in data
    assert "vertical_id" in data
    assert data["model_name"] == "qwen"
    assert data["status"] == "pending"
    assert "message" in data


def test_create_tracking_job_minimal(client: TestClient):
    response = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Test Vertical",
            "brands": [{"display_name": "Brand A"}],
            "prompts": [{"text_en": "Test prompt", "language_original": "en"}],
        },
    )

    assert response.status_code == 201
    data = response.json()
    assert data["model_name"] == "qwen"


def test_create_tracking_job_existing_vertical(client: TestClient):
    first_response = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "SUV Cars",
            "brands": [{"display_name": "VW"}],
            "prompts": [{"text_en": "Test", "language_original": "en"}],
        },
    )

    second_response = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "SUV Cars",
            "brands": [{"display_name": "Toyota"}],
            "prompts": [{"text_en": "Test 2", "language_original": "en"}],
        },
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["vertical_id"] == second_response.json()["vertical_id"]


def test_list_runs_empty(client: TestClient):
    response = client.get("/api/v1/tracking/runs")

    assert response.status_code == 200
    assert response.json() == []


def test_list_runs(client: TestClient):
    job1 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "SUV Cars",
            "brands": [{"display_name": "VW"}],
            "prompts": [{"text_en": "Test", "language_original": "en"}],
            "model_name": "qwen",
        },
    )

    job2 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Smartphones",
            "brands": [{"display_name": "Apple"}],
            "prompts": [{"text_en": "Test", "language_original": "en"}],
            "model_name": "deepseek",
        },
    )

    response = client.get("/api/v1/tracking/runs")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_list_runs_filter_by_vertical(client: TestClient):
    job1 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "SUV Cars",
            "brands": [{"display_name": "VW"}],
            "prompts": [{"text_en": "Test", "language_original": "en"}],
        },
    )

    job2 = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Smartphones",
            "brands": [{"display_name": "Apple"}],
            "prompts": [{"text_en": "Test", "language_original": "en"}],
        },
    )

    vertical_id = job1.json()["vertical_id"]
    response = client.get(f"/api/v1/tracking/runs?vertical_id={vertical_id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["vertical_id"] == vertical_id


def test_list_runs_filter_by_model(client: TestClient):
    client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Test",
            "brands": [{"display_name": "VW"}],
            "prompts": [{"text_en": "Test", "language_original": "en"}],
            "model_name": "qwen",
        },
    )

    client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Test",
            "brands": [{"display_name": "Apple"}],
            "prompts": [{"text_en": "Test", "language_original": "en"}],
            "model_name": "deepseek",
        },
    )

    response = client.get("/api/v1/tracking/runs?model_name=qwen")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["model_name"] == "qwen"


def test_list_runs_pagination(client: TestClient):
    for i in range(5):
        client.post(
            "/api/v1/tracking/jobs",
            json={
                "vertical_name": f"Vertical {i}",
                "brands": [{"display_name": "Brand"}],
                "prompts": [{"text_en": "Test", "language_original": "en"}],
            },
        )

    response = client.get("/api/v1/tracking/runs?skip=2&limit=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2


def test_get_run(client: TestClient):
    job_response = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "SUV Cars",
            "brands": [{"display_name": "VW"}],
            "prompts": [{"text_en": "Test", "language_original": "en"}],
            "model_name": "qwen",
        },
    )

    run_id = job_response.json()["run_id"]
    response = client.get(f"/api/v1/tracking/runs/{run_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == run_id
    assert data["model_name"] == "qwen"
    assert data["status"] == "pending"
    assert "run_time" in data


def test_get_nonexistent_run(client: TestClient):
    response = client.get("/api/v1/tracking/runs/999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]
