import importlib

from fastapi.testclient import TestClient


def test_lifespan_prefetches_embedding_model(monkeypatch):
    app_module = importlib.reload(importlib.import_module("api.app"))
    calls = []

    def fake_ensure(model_name):
        calls.append(model_name)

    monkeypatch.setattr(app_module, "ensure_embedding_model_available", fake_ensure)

    with TestClient(app_module.app):
        pass

    assert calls == [app_module.EMBEDDING_MODEL_NAME]
