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
        config_module = importlib.import_module("services.brand_recognition.config")
        importlib.reload(config_module)
        br_module = importlib.import_module("services.brand_recognition")
        importlib.reload(br_module)
        app_module = importlib.import_module("api.app")
        importlib.reload(app_module)
        with TestClient(app_module.app):
            pass

    assert "embedding" in caplog.text.lower() or "Ollama" in caplog.text


def test_lifespan_skips_logging_when_disabled(monkeypatch, caplog):
    monkeypatch.setenv("ENABLE_EMBEDDING_CLUSTERING", "false")

    with caplog.at_level(logging.INFO):
        config_module = importlib.import_module("services.brand_recognition.config")
        importlib.reload(config_module)
        br_module = importlib.import_module("services.brand_recognition")
        importlib.reload(br_module)
        app_module = importlib.import_module("api.app")
        importlib.reload(app_module)
        with TestClient(app_module.app):
            pass

    assert "Using Ollama embedding model" not in caplog.text
