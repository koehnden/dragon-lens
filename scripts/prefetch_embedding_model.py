import os

from services.brand_recognition import EMBEDDING_MODEL_NAME
from services.model_cache import ensure_embedding_model_available


def prefetch_default_embedding() -> None:
    cache_dir = os.getenv("EMBEDDING_CACHE_DIR")
    ensure_embedding_model_available(EMBEDDING_MODEL_NAME, cache_dir)


if __name__ == "__main__":
    prefetch_default_embedding()
