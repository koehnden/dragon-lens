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

    # First check if the model exists
    try:
        from huggingface_hub import model_info
        model_info(model_name)
        print(f"✓ Model {model_name} exists on Hugging Face Hub")
    except Exception as e:
        raise RuntimeError(f"Model {model_name} not found on Hugging Face Hub: {e}")

    # Try download with HfFileSystem (more reliable than snapshot_download)
    try:
        from huggingface_hub import HfFileSystem
        import shutil

        print(f"Starting download of {model_name} to {target_dir}...")

        fs = HfFileSystem()
        repo_path = f"datasets/{model_name}" if "/" not in model_name else f"models/{model_name}"

        # List all files in the repository
        all_files = fs.glob(f"{repo_path}/**")
        print(f"Found {len(all_files)} files to download")

        # Download each file
        for file_path in all_files:
            if fs.isfile(file_path):
                # Get relative path within repo
                rel_path = file_path.replace(f"{repo_path}/", "")
                local_path = target_dir / rel_path

                # Create directories
                local_path.parent.mkdir(parents=True, exist_ok=True)

                # Download file
                print(f"Downloading {rel_path}...")
                with fs.open(file_path, "rb") as remote_file:
                    with open(local_path, "wb") as local_file:
                        shutil.copyfileobj(remote_file, local_file)

        (target_dir / ".downloaded").touch()
        print(f"✓ Successfully downloaded {model_name}")
        return str(target_dir)

    except Exception as e:
        # If HfFileSystem fails, try snapshot_download as fallback
        print(f"HfFileSystem failed, trying snapshot_download: {e}")
        try:
            from huggingface_hub import snapshot_download

            result = snapshot_download(
                repo_id=model_name,
                local_dir=target_dir,
                local_dir_use_symlinks=False,
                local_files_only=offline_only,
            )
            (target_dir / ".downloaded").touch()
            print(f"✓ Successfully downloaded {model_name} with fallback method")
            return result
        except Exception as fallback_e:
            # Clean up partial download
            import shutil
            if target_dir.exists():
                print(f"Cleaning up partial download due to error: {fallback_e}")
                shutil.rmtree(target_dir, ignore_errors=True)
            raise RuntimeError(f"Failed to download model {model_name}: {fallback_e}")
