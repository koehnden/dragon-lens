"""Integration tests for DeepSeek API integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session

from config import settings
from src.models import APIKey
from src.services.encryption import EncryptionService
from src.services.remote_llms import DeepSeekService


@pytest.fixture
def mock_api_key(db: Session):
    """Create a mock API key in database."""
    encryption_service = EncryptionService(secret_key="test-secret-key")
    encrypted_key = encryption_service.encrypt("test-deepseek-api-key")
    key_hash = encryption_service.hash_key("test-deepseek-api-key")
    
    api_key = APIKey(
        provider="deepseek",
        encrypted_key=encrypted_key,
        key_hash=key_hash,
        is_active=True,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)
    return api_key


def _mock_openai_response(content: str, prompt_tokens: int = 10, completion_tokens: int = 20):
    response = MagicMock()
    response.choices = [MagicMock(message=MagicMock(content=content))]
    response.usage = MagicMock(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    return response


@pytest.mark.asyncio
async def test_deepseek_service_with_db_key(db: Session, mock_api_key, monkeypatch):
    """Test DeepSeekService retrieves API key from database when no env key exists."""
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    service = DeepSeekService(db=db)

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        return_value=_mock_openai_response("Test response")
    )

    with patch("services.base_llm.AsyncOpenAI", return_value=mock_client) as mock_openai:
        answer, tokens_in, tokens_out, latency = await service.query(
            "Test prompt", "deepseek-chat"
        )

    assert answer == "Test response"
    assert tokens_in == 10
    assert tokens_out == 20
    assert isinstance(latency, float)
    assert mock_openai.call_args.kwargs["api_key"] == "test-deepseek-api-key"
    assert mock_openai.call_args.kwargs["base_url"] == settings.deepseek_api_base
    mock_client.chat.completions.create.assert_called_once_with(
        model="deepseek-chat",
        messages=[{"role": "user", "content": "Test prompt"}],
        temperature=service.temperature,
    )


@pytest.mark.asyncio
async def test_deepseek_service_no_api_key(db: Session, monkeypatch):
    """Test DeepSeekService raises when neither env nor DB key exists."""
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    service = DeepSeekService(db=db)

    with pytest.raises(ValueError, match="No active deepseek API key found"):
        await service.query("Test prompt", "deepseek-chat")


@pytest.mark.asyncio
async def test_deepseek_service_inactive_api_key(db: Session, monkeypatch):
    """Test DeepSeekService ignores inactive DB keys when no env key exists."""
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    encryption_service = EncryptionService(secret_key="test-secret-key")
    encrypted_key = encryption_service.encrypt("test-deepseek-api-key")
    key_hash = encryption_service.hash_key("test-deepseek-api-key")

    api_key = APIKey(
        provider="deepseek",
        encrypted_key=encrypted_key,
        key_hash=key_hash,
        is_active=False,
    )
    db.add(api_key)
    db.commit()
    service = DeepSeekService(db=db)

    with pytest.raises(ValueError, match="No active deepseek API key found"):
        await service.query("Test prompt", "deepseek-chat")


@pytest.mark.asyncio
async def test_deepseek_service_sdk_error(db: Session, mock_api_key, monkeypatch):
    """Test DeepSeekService surfaces SDK errors."""
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    service = DeepSeekService(db=db)

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=RuntimeError("DeepSeek API request failed")
    )

    with patch("services.base_llm.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(RuntimeError, match="DeepSeek API request failed"):
            await service.query("Test prompt", "deepseek-chat")


@pytest.mark.asyncio
async def test_deepseek_service_timeout(db: Session, mock_api_key, monkeypatch):
    """Test DeepSeekService handles timeout."""
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    service = DeepSeekService(db=db)

    mock_client = MagicMock()
    mock_client.chat.completions.create = AsyncMock(
        side_effect=TimeoutError("Request timed out")
    )

    with patch("services.base_llm.AsyncOpenAI", return_value=mock_client):
        with pytest.raises(TimeoutError, match="Request timed out"):
            await service.query("Test prompt", "deepseek-chat")


def test_deepseek_service_model_validation():
    """Test DeepSeekService validates model names."""
    service = DeepSeekService(db=None)
    
    valid_models = ["deepseek-chat", "deepseek-reasoner"]
    for model in valid_models:
        service.validate_model(model)
    
    with pytest.raises(ValueError, match="Unsupported DeepSeek model"):
        service.validate_model("invalid-model")
