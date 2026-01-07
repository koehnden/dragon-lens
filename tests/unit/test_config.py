"""Unit tests for configuration."""

from config import Settings


def test_default_settings(monkeypatch):
    """Test that default settings are loaded correctly."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(_env_file=None)

    assert settings.app_name == "DragonLens"
    assert settings.debug is False
    assert settings.database_url == "postgresql+psycopg://dragonlens:dragonlens@localhost:5432/dragonlens"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.ollama_base_url == "http://localhost:11434"


def test_custom_settings(monkeypatch):
    """Test that custom settings can be loaded from environment."""
    monkeypatch.setenv("APP_NAME", "TestApp")
    monkeypatch.setenv("DEBUG", "True")
    monkeypatch.setenv("API_PORT", "9000")

    settings = Settings(_env_file=None)

    assert settings.app_name == "TestApp"
    assert settings.debug is True
    assert settings.api_port == 9000
