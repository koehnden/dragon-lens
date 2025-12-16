import os
from pathlib import Path


def default_cache_dir() -> str:
    custom_dir = os.getenv("HF_HOME")
    if custom_dir:
        return custom_dir
    return str(Path.home() / ".cache" / "huggingface")


def ensure_embedding_model_available(model_name: str, cache_dir: str | None = None) -> str:
    target_dir = cache_dir or default_cache_dir()
    return _download_snapshot(model_name, target_dir)


def _download_snapshot(model_name: str, target_dir: str) -> str:
    from huggingface_hub import snapshot_download

    return snapshot_download(repo_id=model_name, local_dir=target_dir, local_dir_use_symlinks=False)
