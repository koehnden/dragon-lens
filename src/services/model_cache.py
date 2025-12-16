import os
from pathlib import Path


def default_cache_dir() -> str:
    custom_dir = os.getenv("HF_HOME")
    if custom_dir:
        return custom_dir
    return str(Path.home() / ".cache" / "huggingface")


def embedding_cache_dir(model_name: str, cache_dir: str | None = None) -> Path:
    base_dir = Path(cache_dir or default_cache_dir())
    return base_dir / "embeddings" / model_name.replace("/", "__")


def ensure_embedding_model_available(model_name: str, cache_dir: str | None = None, offline_only: bool = False) -> str:
    target_dir = embedding_cache_dir(model_name, cache_dir)
    cached = _is_cached(target_dir)
    if cached:
        return str(target_dir)
    download_offline = offline_only and cached
    return _download_snapshot(model_name, target_dir, download_offline)


def _is_cached(target_dir: Path) -> bool:
    return (target_dir / ".downloaded").exists()


def _download_snapshot(model_name: str, target_dir: Path, offline_only: bool) -> str:
    target_dir.mkdir(parents=True, exist_ok=True)
    from huggingface_hub import snapshot_download

    args = dict(
        repo_id=model_name,
        local_dir=target_dir,
        local_dir_use_symlinks=False,
        local_files_only=offline_only,
    )
    result = snapshot_download(**args)
    (target_dir / ".downloaded").touch()
    return result
