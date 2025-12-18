import pytest


def test_ollama_embedding_model_name_configured():
    from services.brand_recognition import OLLAMA_EMBEDDING_MODEL
    assert "bge-small-zh-v1.5" in OLLAMA_EMBEDDING_MODEL


def test_ollama_service_has_get_embeddings_method():
    from services.ollama import OllamaService
    service = OllamaService()
    assert hasattr(service, "get_embeddings")
