import importlib
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_lifespan_initializes_app_successfully():
    with (
        patch("models.migrations.upgrade_db"),
        patch("models.knowledge_database.init_knowledge_db"),
    ):
        app_module = importlib.reload(importlib.import_module("api.app"))

        with TestClient(app_module.app) as client:
            response = client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "healthy"}
