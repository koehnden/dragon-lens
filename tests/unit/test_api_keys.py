"""Unit tests for API key management."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from src.models import APIKey
from src.services.encryption import EncryptionService


def test_create_api_key(client: TestClient, db: Session):
    """Test creating a new API key."""
    payload = {
        "provider": "deepseek",
        "api_key": "test-api-key-123",
    }

    response = client.post("/api/v1/api-keys", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert data["provider"] == "deepseek"
    assert data["is_active"] is True
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data

    # Verify the key was stored in database
    api_key = db.query(APIKey).filter(APIKey.provider == "deepseek").first()
    assert api_key is not None
    assert api_key.is_active is True
    assert api_key.encrypted_key is not None
    assert api_key.key_hash is not None

    # Verify encryption
    encryption_service = EncryptionService(secret_key="test-secret-key")
    decrypted_key = encryption_service.decrypt(api_key.encrypted_key)
    assert decrypted_key == "test-api-key-123"


def test_create_api_key_duplicate_provider(client: TestClient, db: Session):
    """Test that only one active API key per provider is allowed."""
    # Create first key
    payload1 = {
        "provider": "deepseek",
        "api_key": "first-key",
    }
    response1 = client.post("/api/v1/api-keys", json=payload1)
    assert response1.status_code == 201

    # Try to create second key for same provider
    payload2 = {
        "provider": "deepseek",
        "api_key": "second-key",
    }
    response2 = client.post("/api/v1/api-keys", json=payload2)
    assert response2.status_code == 400
    assert "already exists" in response2.json()["detail"]


def test_list_api_keys(client: TestClient, db: Session):
    """Test listing API keys."""
    # Create test keys
    for provider in ["deepseek", "kimi"]:
        api_key = APIKey(
            provider=provider,
            encrypted_key="encrypted-key",
            key_hash="hash",
            is_active=True,
        )
        db.add(api_key)
    db.commit()

    response = client.get("/api/v1/api-keys")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 2
    assert {item["provider"] for item in data} == {"deepseek", "kimi"}


def test_list_api_keys_filter_provider(client: TestClient, db: Session):
    """Test filtering API keys by provider."""
    # Create test keys
    for provider in ["deepseek", "kimi"]:
        api_key = APIKey(
            provider=provider,
            encrypted_key="encrypted-key",
            key_hash="hash",
            is_active=True,
        )
        db.add(api_key)
    db.commit()

    response = client.get("/api/v1/api-keys?provider=deepseek")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["provider"] == "deepseek"


def test_list_api_keys_filter_active(client: TestClient, db: Session):
    """Test filtering API keys by active status."""
    # Create active and inactive keys
    api_key1 = APIKey(
        provider="deepseek",
        encrypted_key="encrypted-key",
        key_hash="hash",
        is_active=True,
    )
    api_key2 = APIKey(
        provider="kimi",
        encrypted_key="encrypted-key",
        key_hash="hash",
        is_active=False,
    )
    db.add_all([api_key1, api_key2])
    db.commit()

    response = client.get("/api/v1/api-keys?active_only=true")
    assert response.status_code == 200

    data = response.json()
    assert len(data) == 1
    assert data[0]["provider"] == "deepseek"
    assert data[0]["is_active"] is True


def test_get_api_key(client: TestClient, db: Session):
    """Test getting a specific API key."""
    api_key = APIKey(
        provider="deepseek",
        encrypted_key="encrypted-key",
        key_hash="hash",
        is_active=True,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    response = client.get(f"/api/v1/api-keys/{api_key.id}")
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == api_key.id
    assert data["provider"] == "deepseek"
    assert data["is_active"] is True


def test_get_api_key_not_found(client: TestClient):
    """Test getting a non-existent API key."""
    response = client.get("/api/v1/api-keys/999")
    assert response.status_code == 404


def test_update_api_key(client: TestClient, db: Session):
    """Test updating an API key."""
    api_key = APIKey(
        provider="deepseek",
        encrypted_key="old-encrypted-key",
        key_hash="old-hash",
        is_active=True,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    payload = {
        "is_active": False,
    }

    response = client.put(f"/api/v1/api-keys/{api_key.id}", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert data["id"] == api_key.id
    assert data["is_active"] is False

    # Verify update in database
    updated_key = db.query(APIKey).filter(APIKey.id == api_key.id).first()
    assert updated_key.is_active is False


def test_update_api_key_with_new_key(client: TestClient, db: Session):
    """Test updating an API key with a new key value."""
    api_key = APIKey(
        provider="deepseek",
        encrypted_key="old-encrypted-key",
        key_hash="old-hash",
        is_active=True,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    payload = {
        "api_key": "new-test-key",
    }

    response = client.put(f"/api/v1/api-keys/{api_key.id}", json=payload)
    assert response.status_code == 200

    # Verify the key was updated
    updated_key = db.query(APIKey).filter(APIKey.id == api_key.id).first()
    assert updated_key.encrypted_key != "old-encrypted-key"
    assert updated_key.key_hash != "old-hash"


def test_delete_api_key(client: TestClient, db: Session):
    """Test deleting an API key."""
    api_key = APIKey(
        provider="deepseek",
        encrypted_key="encrypted-key",
        key_hash="hash",
        is_active=True,
    )
    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    response = client.delete(f"/api/v1/api-keys/{api_key.id}")
    assert response.status_code == 204

    # Verify deletion
    deleted_key = db.query(APIKey).filter(APIKey.id == api_key.id).first()
    assert deleted_key is None


def test_delete_api_key_not_found(client: TestClient):
    """Test deleting a non-existent API key."""
    response = client.delete("/api/v1/api-keys/999")
    assert response.status_code == 404
