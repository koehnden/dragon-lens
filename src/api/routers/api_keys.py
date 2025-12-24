"""API router for API key management."""

import logging
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from models import APIKey, get_db
from models.schemas import (
    APIKeyCreate,
    APIKeyResponse,
    APIKeyUpdate,
)
from services.encryption import EncryptionService, APIKeyManager

logger = logging.getLogger(__name__)

router = APIRouter()
security = HTTPBearer()


def get_encryption_service() -> EncryptionService:
    return EncryptionService()


def get_api_key_manager(
    encryption_service: EncryptionService = Depends(get_encryption_service),
) -> APIKeyManager:
    return APIKeyManager(encryption_service)


@router.post("/api-keys", response_model=APIKeyResponse, status_code=201)
async def create_api_key(
    api_key_data: APIKeyCreate,
    db: Session = Depends(get_db),
    api_key_manager: APIKeyManager = Depends(get_api_key_manager),
) -> APIKeyResponse:
    """
    Store an API key for a specific provider.

    The API key will be encrypted before storage.
    Only one active API key per provider is allowed.
    """
    existing_key = (
        db.query(APIKey)
        .filter(
            APIKey.provider == api_key_data.provider,
            APIKey.is_active == True,
        )
        .first()
    )

    if existing_key:
        raise HTTPException(
            status_code=400,
            detail=f"An active API key already exists for provider '{api_key_data.provider}'. "
            "Please deactivate it first or update the existing key.",
        )

    encrypted_key, key_hash = api_key_manager.store_api_key(
        api_key_data.provider, api_key_data.api_key
    )

    api_key = APIKey(
        provider=api_key_data.provider,
        encrypted_key=encrypted_key,
        key_hash=key_hash,
        is_active=True,
    )

    db.add(api_key)
    db.commit()
    db.refresh(api_key)

    return APIKeyResponse(
        id=api_key.id,
        provider=api_key.provider,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        updated_at=api_key.updated_at,
    )


@router.get("/api-keys", response_model=List[APIKeyResponse])
async def list_api_keys(
    provider: str | None = None,
    active_only: bool = True,
    db: Session = Depends(get_db),
) -> List[APIKeyResponse]:
    """
    List API keys with optional filters.

    Args:
        provider: Filter by provider (qwen, deepseek, kimi)
        active_only: Only return active keys
        db: Database session

    Returns:
        List of API keys (without the actual key values)
    """
    query = db.query(APIKey)

    if provider:
        query = query.filter(APIKey.provider == provider)
    if active_only:
        query = query.filter(APIKey.is_active == True)

    api_keys = query.order_by(APIKey.provider, APIKey.created_at.desc()).all()

    return [
        APIKeyResponse(
            id=key.id,
            provider=key.provider,
            is_active=key.is_active,
            created_at=key.created_at,
            updated_at=key.updated_at,
        )
        for key in api_keys
    ]


@router.get("/api-keys/{key_id}", response_model=APIKeyResponse)
async def get_api_key(
    key_id: int,
    db: Session = Depends(get_db),
) -> APIKeyResponse:
    """
    Get details of a specific API key.

    Args:
        key_id: API key ID
        db: Database session

    Returns:
        API key details (without the actual key value)

    Raises:
        HTTPException: If key not found
    """
    api_key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not api_key:
        raise HTTPException(status_code=404, detail=f"API key {key_id} not found")

    return APIKeyResponse(
        id=api_key.id,
        provider=api_key.provider,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        updated_at=api_key.updated_at,
    )


@router.put("/api-keys/{key_id}", response_model=APIKeyResponse)
async def update_api_key(
    key_id: int,
    api_key_update: APIKeyUpdate,
    db: Session = Depends(get_db),
    api_key_manager: APIKeyManager = Depends(get_api_key_manager),
) -> APIKeyResponse:
    """
    Update an API key.

    Can update the API key value or toggle active status.
    """
    api_key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not api_key:
        raise HTTPException(status_code=404, detail=f"API key {key_id} not found")

    if api_key_update.api_key is not None:
        encrypted_key, key_hash = api_key_manager.store_api_key(
            api_key.provider, api_key_update.api_key
        )
        api_key.encrypted_key = encrypted_key
        api_key.key_hash = key_hash

    if api_key_update.is_active is not None:
        api_key.is_active = api_key_update.is_active

    db.commit()
    db.refresh(api_key)

    return APIKeyResponse(
        id=api_key.id,
        provider=api_key.provider,
        is_active=api_key.is_active,
        created_at=api_key.created_at,
        updated_at=api_key.updated_at,
    )


@router.delete("/api-keys/{key_id}", status_code=204)
async def delete_api_key(
    key_id: int,
    db: Session = Depends(get_db),
) -> None:
    """
    Delete an API key.

    Args:
        key_id: API key ID
        db: Database session

    Raises:
        HTTPException: If key not found
    """
    api_key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not api_key:
        raise HTTPException(status_code=404, detail=f"API key {key_id} not found")

    db.delete(api_key)
    db.commit()


@router.get("/api-keys/{key_id}/decrypt", response_model=dict)
async def decrypt_api_key(
    key_id: int,
    credentials: HTTPAuthorizationCredentials = Security(security),
    db: Session = Depends(get_db),
    api_key_manager: APIKeyManager = Depends(get_api_key_manager),
) -> dict:
    """
    Decrypt and return an API key (admin only).

    Requires authentication.
    """
    # TODO: Implement proper authentication
    # For now, just check for a basic token
    if credentials.credentials != "admin-token":
        raise HTTPException(status_code=401, detail="Unauthorized")

    api_key = db.query(APIKey).filter(APIKey.id == key_id).first()
    if not api_key:
        raise HTTPException(status_code=404, detail=f"API key {key_id} not found")

    try:
        decrypted_key = api_key_manager.retrieve_api_key(api_key.encrypted_key)
        return {
            "id": api_key.id,
            "provider": api_key.provider,
            "api_key": decrypted_key,
            "is_active": api_key.is_active,
        }
    except Exception as e:
        logger.error(f"Failed to decrypt API key {key_id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to decrypt API key")
