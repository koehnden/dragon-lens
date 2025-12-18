import importlib
import logging

from fastapi.testclient import TestClient


def test_lifespan_initializes_app_successfully():
    app_module = importlib.reload(importlib.import_module("api.app"))

    with TestClient(app_module.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


def test_lifespan_logs_embedding_model_when_enabled(monkeypatch, caplog):
    monkeypatch.setenv("ENABLE_EMBEDDING_CLUSTERING", "true")

    with caplog.at_level(logging.INFO):
        importlib.reload(importlib.import_module("services.brand_recognition"))
        app_module = importlib.reload(importlib.import_module("api.app"))
        with TestClient(app_module.app):
            pass

    assert "qllama/bge-small-zh-v1.5" in caplog.text or "Ollama embedding model" in caplog.text


def test_lifespan_skips_logging_when_disabled(monkeypatch, caplog):
    monkeypatch.setenv("ENABLE_EMBEDDING_CLUSTERING", "false")

    with caplog.at_level(logging.INFO):
        importlib.reload(importlib.import_module("services.brand_recognition"))
        app_module = importlib.reload(importlib.import_module("api.app"))
        with TestClient(app_module.app):
            pass

    assert "Using Ollama embedding model" not in caplog.text
