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
