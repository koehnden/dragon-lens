import subprocess

from services.brand_recognition import OLLAMA_EMBEDDING_MODEL


def prefetch_ollama_embedding_model() -> None:
    print(f"Pulling Ollama embedding model: {OLLAMA_EMBEDDING_MODEL}")
    result = subprocess.run(["ollama", "pull", OLLAMA_EMBEDDING_MODEL], capture_output=True, text=True)
    if result.returncode == 0:
        print(f"Successfully pulled {OLLAMA_EMBEDDING_MODEL}")
    else:
        print(f"Failed to pull {OLLAMA_EMBEDDING_MODEL}: {result.stderr}")
        raise RuntimeError(f"Failed to pull Ollama model: {result.stderr}")


if __name__ == "__main__":
    prefetch_ollama_embedding_model()
