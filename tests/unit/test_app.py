"""Unit tests for root API endpoints."""

import pytest
from fastapi.testclient import TestClient


def test_root(client: TestClient):
    response = client.get("/")

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "DragonLens"
    assert data["version"] == "0.1.0"
    assert data["status"] == "running"


def test_health(client: TestClient):
    response = client.get("/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
