"""Unit tests for configuration."""

from config import Settings


def test_default_settings(monkeypatch):
    """Test that default settings are loaded correctly."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("KNOWLEDGE_DATABASE_URL", raising=False)
    monkeypatch.delenv("BACKEND_API_BASE_URL", raising=False)
    monkeypatch.delenv("APP_MODE", raising=False)
    settings = Settings(_env_file=None)

    assert settings.app_name == "DragonLens"
    assert settings.debug is False
    assert settings.app_mode == "local_admin"
    assert (
        settings.database_url
        == "postgresql+psycopg://dragonlens:dragonlens@localhost:5432/dragonlens"
    )
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.resolved_backend_api_base_url == "http://localhost:8000"
    assert settings.resolved_knowledge_database_url == "sqlite:///./data/knowledge.db"


def test_custom_settings(monkeypatch):
    """Test that custom settings can be loaded from environment."""
    monkeypatch.setenv("APP_NAME", "TestApp")
    monkeypatch.setenv("DEBUG", "True")
    monkeypatch.setenv("API_PORT", "9000")
    monkeypatch.setenv("APP_MODE", "public_demo")
    monkeypatch.setenv("BACKEND_API_BASE_URL", "https://demo.dragon-lens.ai/api")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db:5432/app")
    monkeypatch.setenv("KNOWLEDGE_DATABASE_URL", "")

    settings = Settings(_env_file=None)

    assert settings.app_name == "TestApp"
    assert settings.debug is True
    assert settings.api_port == 9000
    assert settings.app_mode == "public_demo"
    assert settings.is_public_demo is True
    assert settings.resolved_backend_api_base_url == "https://demo.dragon-lens.ai/api"
    assert (
        settings.resolved_knowledge_database_url
        == "postgresql+psycopg://user:pass@db:5432/app"
    )
