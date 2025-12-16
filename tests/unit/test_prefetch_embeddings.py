import importlib


def test_prefetch_default_embedding_uses_cache_env(monkeypatch, tmp_path):
    module = importlib.reload(importlib.import_module("scripts.prefetch_embedding_model"))
    calls = []

    def fake_ensure(model_name, cache_dir=None):
        calls.append((model_name, cache_dir))

    monkeypatch.setenv("EMBEDDING_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(module, "ensure_embedding_model_available", fake_ensure)

    module.prefetch_default_embedding()

    assert calls == [(module.EMBEDDING_MODEL_NAME, str(tmp_path))]
