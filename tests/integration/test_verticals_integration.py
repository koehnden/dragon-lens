"""Integration tests for verticals API endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_vertical_crud_workflow(client: TestClient):
    """Test complete CRUD workflow for verticals."""
    # Create a vertical
    create_response = client.post(
        "/api/v1/verticals",
        json={
            "name": "Luxury Cars",
            "description": "Premium automotive brands",
        },
    )
    assert create_response.status_code == 201
    vertical_data = create_response.json()
    vertical_id = vertical_data["id"]
    assert vertical_data["name"] == "Luxury Cars"

    # Read the vertical
    get_response = client.get(f"/api/v1/verticals/{vertical_id}")
    assert get_response.status_code == 200
    assert get_response.json()["id"] == vertical_id
    assert get_response.json()["name"] == "Luxury Cars"

    # List verticals
    list_response = client.get("/api/v1/verticals")
    assert list_response.status_code == 200
    verticals = list_response.json()
    assert len(verticals) >= 1
    assert any(v["id"] == vertical_id for v in verticals)


def test_multiple_verticals_isolation(client: TestClient):
    """Test that multiple verticals are properly isolated."""
    # Create first vertical
    v1 = client.post(
        "/api/v1/verticals",
        json={"name": "SUV Cars", "description": "Sport utility vehicles"},
    )
    v1_id = v1.json()["id"]

    # Create second vertical
    v2 = client.post(
        "/api/v1/verticals",
        json={"name": "Smartphones", "description": "Mobile devices"},
    )
    v2_id = v2.json()["id"]

    # Verify both exist independently
    assert v1_id != v2_id

    v1_get = client.get(f"/api/v1/verticals/{v1_id}")
    assert v1_get.json()["name"] == "SUV Cars"

    v2_get = client.get(f"/api/v1/verticals/{v2_id}")
    assert v2_get.json()["name"] == "Smartphones"

    # List should show both
    list_resp = client.get("/api/v1/verticals")
    names = [v["name"] for v in list_resp.json()]
    assert "SUV Cars" in names
    assert "Smartphones" in names


def test_vertical_name_uniqueness(client: TestClient):
    """Test that vertical names must be unique."""
    # Create first vertical
    client.post(
        "/api/v1/verticals",
        json={"name": "Electric Cars"},
    )

    # Attempt to create duplicate
    duplicate = client.post(
        "/api/v1/verticals",
        json={"name": "Electric Cars"},
    )

    assert duplicate.status_code == 400
    assert "already exists" in duplicate.json()["detail"].lower()


def test_vertical_pagination_consistency(client: TestClient):
    """Test pagination returns consistent results."""
    # Create multiple verticals
    for i in range(10):
        client.post(
            "/api/v1/verticals",
            json={"name": f"Vertical {i:02d}"},
        )

    # Get first page
    page1 = client.get("/api/v1/verticals?skip=0&limit=5")
    assert len(page1.json()) == 5

    # Get second page
    page2 = client.get("/api/v1/verticals?skip=5&limit=5")
    assert len(page2.json()) == 5

    # Ensure no overlap
    page1_ids = {v["id"] for v in page1.json()}
    page2_ids = {v["id"] for v in page2.json()}
    assert len(page1_ids & page2_ids) == 0


def test_vertical_with_empty_description(client: TestClient):
    """Test vertical creation without description."""
    response = client.post(
        "/api/v1/verticals",
        json={"name": "Test Vertical"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Vertical"
    assert data["description"] is None
