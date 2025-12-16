import importlib
from unittest.mock import patch

from fastapi.testclient import TestClient


def test_lifespan_initializes_app_successfully():
    app_module = importlib.reload(importlib.import_module("api.app"))

    with TestClient(app_module.app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}


def test_lifespan_caches_embedding_model_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("ENABLE_EMBEDDING_CLUSTERING", "true")
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    cache_calls = []

    def fake_ensure(model_name, cache_dir=None, offline_only=False):
        cache_calls.append(model_name)
        target = tmp_path / "embeddings" / model_name.replace("/", "__")
        target.mkdir(parents=True, exist_ok=True)
        (target / ".downloaded").touch()
        return str(target)

    with patch("services.model_cache.ensure_embedding_model_available", fake_ensure):
        importlib.reload(importlib.import_module("services.brand_recognition"))
        app_module = importlib.reload(importlib.import_module("api.app"))
        with TestClient(app_module.app):
            pass

    assert "BAAI/bge-small-zh-v1.5" in cache_calls


def test_lifespan_skips_caching_when_disabled(monkeypatch):
    monkeypatch.setenv("ENABLE_EMBEDDING_CLUSTERING", "false")
    cache_calls = []

    def fake_ensure(model_name, cache_dir=None, offline_only=False):
        cache_calls.append(model_name)
        return "/fake/path"

    with patch("services.model_cache.ensure_embedding_model_available", fake_ensure):
        importlib.reload(importlib.import_module("services.brand_recognition"))
        app_module = importlib.reload(importlib.import_module("api.app"))
        with TestClient(app_module.app):
            pass

    assert cache_calls == []
