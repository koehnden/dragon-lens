from pathlib import Path

import pytest

from services import model_cache


def test_ensure_embedding_model_uses_env_cache(monkeypatch, tmp_path):
    calls = []

    def fake_download(repo_id, target_dir, offline_only):
        calls.append((repo_id, target_dir, offline_only))
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / ".downloaded").touch()
        return str(target_dir / "model")

    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr(model_cache, "_download_snapshot", fake_download)

    result = model_cache.ensure_embedding_model_available("BAAI/bge-m3")

    expected_dir = tmp_path / "embeddings" / "BAAI__bge-m3"
    assert result == str(expected_dir / "model")
    assert calls == [("BAAI/bge-m3", expected_dir, False)]


def test_ensure_embedding_model_prefers_explicit_cache(monkeypatch, tmp_path):
    calls = []

    def fake_download(repo_id, target_dir, offline_only):
        calls.append((repo_id, target_dir, offline_only))
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / ".downloaded").touch()
        return str(target_dir / "model")

    monkeypatch.setenv("HF_HOME", str(tmp_path / "ignored"))
    monkeypatch.setattr(model_cache, "_download_snapshot", fake_download)

    cache_dir = tmp_path / "explicit"
    result = model_cache.ensure_embedding_model_available("BAAI/bge-m3", str(cache_dir))

    expected_dir = cache_dir / "embeddings" / "BAAI__bge-m3"
    assert result == str(expected_dir / "model")
    assert calls == [("BAAI/bge-m3", expected_dir, False)]


def test_ensure_embedding_model_skips_when_marker_present(monkeypatch, tmp_path):
    target_dir = tmp_path / "embeddings" / "BAAI__bge-m3"
    target_dir.mkdir(parents=True)
    (target_dir / ".downloaded").touch()

    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr(model_cache, "_download_snapshot", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("should not run")))

    result = model_cache.ensure_embedding_model_available("BAAI/bge-m3")

    assert result == str(target_dir)


def test_offline_download_falls_back_online(monkeypatch, tmp_path):
    calls = []

    def fake_download(repo_id, target_dir, offline_only):
        calls.append(offline_only)
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / ".downloaded").touch()
        return str(target_dir)

    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setattr(model_cache, "_download_snapshot", fake_download)

    result = model_cache.ensure_embedding_model_available("BAAI/bge-m3", offline_only=True)

    assert result == str(tmp_path / "embeddings" / "BAAI__bge-m3")
    assert calls == [False]
