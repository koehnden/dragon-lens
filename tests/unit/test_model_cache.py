from pathlib import Path

import pytest

from services import model_cache


def test_ensure_embedding_model_uses_env_cache(monkeypatch, tmp_path):
    calls = []

    def fake_download(repo_id, local_dir):
        calls.append((repo_id, Path(local_dir)))
        return str(tmp_path / "model")

    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr(model_cache, "_download_snapshot", fake_download)

    result = model_cache.ensure_embedding_model_available("BAAI/bge-m3")

    assert result == str(tmp_path / "model")
    assert calls == [("BAAI/bge-m3", tmp_path)]


def test_ensure_embedding_model_prefers_explicit_cache(monkeypatch, tmp_path):
    calls = []

    def fake_download(repo_id, local_dir):
        calls.append((repo_id, Path(local_dir)))
        return str(Path(local_dir) / "model")

    monkeypatch.setenv("HF_HOME", str(tmp_path / "ignored"))
    monkeypatch.setattr(model_cache, "_download_snapshot", fake_download)

    cache_dir = tmp_path / "explicit"
    result = model_cache.ensure_embedding_model_available("BAAI/bge-m3", str(cache_dir))

    assert result == str(cache_dir / "model")
    assert calls == [("BAAI/bge-m3", cache_dir)]
