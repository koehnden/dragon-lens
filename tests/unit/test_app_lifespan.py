import importlib

from fastapi.testclient import TestClient


def test_lifespan_initializes_app_successfully():
    app_module = importlib.reload(importlib.import_module("api.app"))

    with TestClient(app_module.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}
