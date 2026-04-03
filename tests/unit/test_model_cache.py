def test_ollama_service_has_query_entrypoint():
    from services.ollama import OllamaService

    service = OllamaService()

    assert hasattr(service, "query_main_model")
