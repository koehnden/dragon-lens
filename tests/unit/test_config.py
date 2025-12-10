"""Unit tests for configuration."""

import pytest

from src.config import Settings


def test_default_settings():
    """Test that default settings are loaded correctly."""
    settings = Settings()

    assert settings.app_name == "DragonLens"
    assert settings.debug is False
    assert settings.database_url == "sqlite:///./dragonlens.db"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.ollama_base_url == "http://localhost:11434"


def test_custom_settings(monkeypatch):
    """Test that custom settings can be loaded from environment."""
    monkeypatch.setenv("APP_NAME", "TestApp")
    monkeypatch.setenv("DEBUG", "True")
    monkeypatch.setenv("API_PORT", "9000")

    settings = Settings()

    assert settings.app_name == "TestApp"
    assert settings.debug is True
    assert settings.api_port == 9000
