"""Encryption service for securely storing API keys."""

import base64
import hashlib
import logging
import os
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.config import settings

logger = logging.getLogger(__name__)


class EncryptionService:
    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or os.getenv("ENCRYPTION_SECRET_KEY") or settings.encryption_secret_key
        
        if self.secret_key == "ENCRYPTION_SECRET_KEY_NOT_SET_PLEASE_SET_IN_ENV":
            raise ValueError(
                "ENCRYPTION_SECRET_KEY is not configured. "
                "Please set ENCRYPTION_SECRET_KEY environment variable or add it to your .env file. "
                "This is required for secure API key storage. "
                "You can generate a secure key with: "
                "python -c 'import secrets; print(secrets.token_hex(32))'"
            )
        
        self.salt = b"dragon_lens_salt"
        self._fernet = self._create_fernet()

    def _create_fernet(self) -> Fernet:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=self.salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(self.secret_key.encode()))
        return Fernet(key)

    def encrypt(self, plaintext: str) -> str:
        encrypted = self._fernet.encrypt(plaintext.encode())
        return encrypted.decode()

    def decrypt(self, ciphertext: str) -> str:
        try:
            decrypted = self._fernet.decrypt(ciphertext.encode())
            return decrypted.decode()
        except InvalidToken:
            raise ValueError("Invalid encrypted key")

    @staticmethod
    def hash_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()


class APIKeyManager:
    def __init__(self, encryption_service: EncryptionService):
        self.encryption_service = encryption_service

    def store_api_key(self, provider: str, api_key: str) -> tuple[str, str]:
        encrypted_key = self.encryption_service.encrypt(api_key)
        key_hash = self.encryption_service.hash_key(api_key)
        return encrypted_key, key_hash

    def retrieve_api_key(self, encrypted_key: str) -> str:
        return self.encryption_service.decrypt(encrypted_key)

    def verify_api_key(self, api_key: str, stored_hash: str) -> bool:
        return self.encryption_service.hash_key(api_key) == stored_hash
