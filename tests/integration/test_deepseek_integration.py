"""Integration tests for DeepSeek API integration."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.orm import Session

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


@pytest.mark.asyncio
async def test_deepseek_service_with_db_key(db: Session, mock_api_key):
    """Test DeepSeekService retrieves API key from database."""
    service = DeepSeekService(db=db)
    
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "Test response"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 20},
    }
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        answer, tokens_in, tokens_out, latency = await service.query(
            "Test prompt", "deepseek-chat"
        )
        
        assert answer == "Test response"
        assert tokens_in == 10
        assert tokens_out == 20
        assert isinstance(latency, float)
        
        call_args = mock_post.call_args
        assert call_args is not None
        assert "Authorization" in call_args[1]["headers"]
        assert call_args[1]["headers"]["Authorization"] == "Bearer test-deepseek-api-key"


@pytest.mark.asyncio
async def test_deepseek_service_no_api_key(db: Session):
    """Test DeepSeekService raises error when no API key found."""
    service = DeepSeekService(db=db)
    
    with pytest.raises(ValueError, match="No active API key found for provider deepseek"):
        await service.query("Test prompt", "deepseek-chat")


@pytest.mark.asyncio
async def test_deepseek_service_inactive_api_key(db: Session):
    """Test DeepSeekService ignores inactive API keys."""
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
    
    with pytest.raises(ValueError, match="No active API key found for provider deepseek"):
        await service.query("Test prompt", "deepseek-chat")


@pytest.mark.asyncio
async def test_deepseek_service_http_error(db: Session, mock_api_key):
    """Test DeepSeekService handles HTTP errors."""
    service = DeepSeekService(db=db)
    
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized"
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_response
        
        with pytest.raises(Exception, match="DeepSeek API request failed"):
            await service.query("Test prompt", "deepseek-chat")


@pytest.mark.asyncio
async def test_deepseek_service_timeout(db: Session, mock_api_key):
    """Test DeepSeekService handles timeout."""
    service = DeepSeekService(db=db)
    
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = TimeoutError("Request timed out")
        
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
