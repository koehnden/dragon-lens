"""Unit tests for verticals API endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_create_vertical(client: TestClient):
    response = client.post(
        "/api/v1/verticals",
        json={"name": "SUV Cars", "description": "Sport utility vehicles"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "SUV Cars"
    assert data["description"] == "Sport utility vehicles"
    assert "id" in data
    assert "created_at" in data


def test_create_duplicate_vertical(client: TestClient):
    client.post(
        "/api/v1/verticals",
        json={"name": "SUV Cars", "description": "Sport utility vehicles"},
    )

    response = client.post(
        "/api/v1/verticals",
        json={"name": "SUV Cars", "description": "Different description"},
    )

    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]


def test_list_verticals_empty(client: TestClient):
    response = client.get("/api/v1/verticals")

    assert response.status_code == 200
    assert response.json() == []


def test_list_verticals(client: TestClient):
    client.post("/api/v1/verticals", json={"name": "SUV Cars"})
    client.post("/api/v1/verticals", json={"name": "Smartphones"})

    response = client.get("/api/v1/verticals")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "SUV Cars"
    assert data[1]["name"] == "Smartphones"


def test_list_verticals_pagination(client: TestClient):
    for i in range(5):
        client.post("/api/v1/verticals", json={"name": f"Vertical {i}"})

    response = client.get("/api/v1/verticals?skip=2&limit=2")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["name"] == "Vertical 2"
    assert data[1]["name"] == "Vertical 3"


def test_get_vertical(client: TestClient):
    create_response = client.post(
        "/api/v1/verticals",
        json={"name": "SUV Cars", "description": "Sport utility vehicles"},
    )
    vertical_id = create_response.json()["id"]

    response = client.get(f"/api/v1/verticals/{vertical_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == vertical_id
    assert data["name"] == "SUV Cars"
    assert data["description"] == "Sport utility vehicles"


def test_get_nonexistent_vertical(client: TestClient):
    response = client.get("/api/v1/verticals/999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"]


def test_create_vertical_minimal(client: TestClient):
    response = client.post("/api/v1/verticals", json={"name": "Test Vertical"})

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Vertical"
    assert data["description"] is None


def test_delete_vertical_success(client: TestClient):
    create_response = client.post(
        "/api/v1/verticals",
        json={"name": "SUV Cars", "description": "Sport utility vehicles"},
    )
    vertical_id = create_response.json()["id"]

    response = client.delete(f"/api/v1/verticals/{vertical_id}")

    assert response.status_code == 200
    data = response.json()
    assert data["vertical_id"] == vertical_id
    assert data["deleted"] is True
    assert data["deleted_runs_count"] == 0
    assert "deleted" in data["message"].lower()


def test_delete_vertical_with_completed_runs(client: TestClient, db_session):
    from models import Run, RunStatus, Vertical

    vertical = Vertical(name="SUV Cars", description="Sport utility vehicles")
    db_session.add(vertical)
    db_session.commit()
    db_session.refresh(vertical)

    run1 = Run(
        vertical_id=vertical.id,
        model_name="qwen2.5:7b",
        status=RunStatus.COMPLETED
    )
    run2 = Run(
        vertical_id=vertical.id,
        model_name="qwen2.5:7b",
        status=RunStatus.FAILED
    )
    db_session.add(run1)
    db_session.add(run2)
    db_session.commit()

    response = client.delete(f"/api/v1/verticals/{vertical.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["vertical_id"] == vertical.id
    assert data["deleted"] is True
    assert data["deleted_runs_count"] == 2


def test_delete_vertical_with_in_progress_runs(client: TestClient, db_session):
    from models import Run, RunStatus, Vertical

    vertical = Vertical(name="SUV Cars", description="Sport utility vehicles")
    db_session.add(vertical)
    db_session.commit()
    db_session.refresh(vertical)

    run1 = Run(
        vertical_id=vertical.id,
        model_name="qwen2.5:7b",
        status=RunStatus.IN_PROGRESS
    )
    run2 = Run(
        vertical_id=vertical.id,
        model_name="qwen2.5:7b",
        status=RunStatus.PENDING
    )
    db_session.add(run1)
    db_session.add(run2)
    db_session.commit()

    response = client.delete(f"/api/v1/verticals/{vertical.id}")

    assert response.status_code == 409
    data = response.json()
    assert "detail" in data
    assert "error" in data["detail"]
    assert "DELETE_CONFLICT" in data["detail"]["error"]["code"]
    assert "in progress" in data["detail"]["error"]["message"].lower()


def test_delete_nonexistent_vertical(client: TestClient):
    response = client.delete("/api/v1/verticals/999")

    assert response.status_code == 404
    data = response.json()
    assert "detail" in data
    assert "error" in data["detail"]
    assert "VERTICAL_NOT_FOUND" in data["detail"]["error"]["code"]


def test_delete_vertical_cascades_brands(client: TestClient, db_session):
    from models import Brand, Vertical

    vertical = Vertical(name="SUV Cars", description="Sport utility vehicles")
    db_session.add(vertical)
    db_session.commit()
    db_session.refresh(vertical)

    brand = Brand(
        vertical_id=vertical.id,
        display_name="Tesla",
        aliases={"zh": ["特斯拉"], "en": ["Tesla"]},
    )
    db_session.add(brand)
    db_session.commit()

    response = client.delete(f"/api/v1/verticals/{vertical.id}")

    assert response.status_code == 200

    remaining_brands = db_session.query(Brand).filter(Brand.vertical_id == vertical.id).all()
    assert len(remaining_brands) == 0


def test_delete_vertical_cascades_prompts(client: TestClient, db_session):
    from models import Prompt, PromptLanguage, Vertical

    vertical = Vertical(name="SUV Cars", description="Sport utility vehicles")
    db_session.add(vertical)
    db_session.commit()
    db_session.refresh(vertical)

    prompt = Prompt(
        vertical_id=vertical.id,
        text_zh="推荐一款SUV汽车",
        text_en="Recommend an SUV car",
        language_original=PromptLanguage.EN,
    )
    db_session.add(prompt)
    db_session.commit()

    response = client.delete(f"/api/v1/verticals/{vertical.id}")

    assert response.status_code == 200

    remaining_prompts = db_session.query(Prompt).filter(Prompt.vertical_id == vertical.id).all()
    assert len(remaining_prompts) == 0
