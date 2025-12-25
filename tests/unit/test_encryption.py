"""Unit tests for encryption service."""

import pytest
from src.services.encryption import EncryptionService, APIKeyManager


def test_encryption_service_encrypt_decrypt():
    """Test encryption and decryption roundtrip."""
    service = EncryptionService(secret_key="test-secret-key-1234567890123456")
    
    plaintext = "test-api-key-123"
    encrypted = service.encrypt(plaintext)
    decrypted = service.decrypt(encrypted)
    
    assert decrypted == plaintext
    assert encrypted != plaintext


def test_encryption_service_different_keys():
    """Test that different keys produce different encrypted values."""
    service1 = EncryptionService(secret_key="key1-1234567890123456")
    service2 = EncryptionService(secret_key="key2-1234567890123456")
    
    plaintext = "same-api-key"
    encrypted1 = service1.encrypt(plaintext)
    encrypted2 = service2.encrypt(plaintext)
    
    assert encrypted1 != encrypted2
    assert service1.decrypt(encrypted1) == plaintext
    assert service2.decrypt(encrypted2) == plaintext


def test_encryption_service_hash_key():
    """Test key hashing."""
    service = EncryptionService(secret_key="test-secret-key")
    
    api_key = "test-api-key-123"
    hash1 = service.hash_key(api_key)
    hash2 = service.hash_key(api_key)
    
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA256 hex digest length


def test_encryption_service_hash_key_different():
    """Test that different keys produce different hashes."""
    service = EncryptionService(secret_key="test-secret-key")
    
    hash1 = service.hash_key("key1")
    hash2 = service.hash_key("key2")
    
    assert hash1 != hash2


def test_api_key_manager_store_retrieve():
    """Test API key manager store and retrieve."""
    encryption_service = EncryptionService(secret_key="test-secret-key-1234567890123456")
    manager = APIKeyManager(encryption_service)
    
    provider = "deepseek"
    api_key = "test-api-key-123"
    
    encrypted_key, key_hash = manager.store_api_key(provider, api_key)
    
    assert encrypted_key is not None
    assert key_hash is not None
    assert key_hash == encryption_service.hash_key(api_key)
    
    decrypted_key = manager.retrieve_api_key(encrypted_key)
    assert decrypted_key == api_key


def test_api_key_manager_different_providers():
    """Test API key manager with different providers."""
    encryption_service = EncryptionService(secret_key="test-secret-key")
    manager = APIKeyManager(encryption_service)
    
    providers = ["deepseek", "kimi", "qwen"]
    for provider in providers:
        api_key = f"{provider}-api-key"
        encrypted_key, key_hash = manager.store_api_key(provider, api_key)
        
        decrypted_key = manager.retrieve_api_key(encrypted_key)
        assert decrypted_key == api_key


def test_api_key_manager_invalid_encrypted_key():
    """Test API key manager with invalid encrypted key."""
    encryption_service = EncryptionService(secret_key="test-secret-key")
    manager = APIKeyManager(encryption_service)
    
    with pytest.raises(ValueError, match="Invalid encrypted key"):
        manager.retrieve_api_key("invalid-encrypted-key")


def test_api_key_manager_tampered_encrypted_key():
    """Test API key manager with tampered encrypted key."""
    encryption_service = EncryptionService(secret_key="test-secret-key")
    manager = APIKeyManager(encryption_service)
    
    encrypted_key, _ = manager.store_api_key("deepseek", "test-key")
    tampered_key = encrypted_key[:-1] + "X"  # Change last character
    
    with pytest.raises(ValueError, match="Invalid encrypted key"):
        manager.retrieve_api_key(tampered_key)
