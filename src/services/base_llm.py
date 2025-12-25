import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from src.models import APIKey
from src.models.domain import LLMProvider
from src.services.encryption import EncryptionService

logger = logging.getLogger(__name__)


class BaseLLMService(ABC):
    provider: LLMProvider
    default_model: str
    api_base: str

    def __init__(self, db: Optional[Session] = None, api_key: Optional[str] = None):
        self.db = db
        self._api_key = api_key
        self._encryption_service: Optional[EncryptionService] = None

    def _get_encryption_service(self) -> EncryptionService:
        if self._encryption_service is None:
            self._encryption_service = EncryptionService()
        return self._encryption_service

    def _get_api_key(self) -> str:
        if self._api_key:
            return self._api_key

        if not self.db:
            raise ValueError("Database session required when api_key not provided")

        api_key_record = (
            self.db.query(APIKey)
            .filter(
                APIKey.provider == self.provider.value,
                APIKey.is_active == True,
            )
            .first()
        )

        if not api_key_record:
            raise ValueError(f"No active {self.provider.value} API key found")

        return self._get_encryption_service().decrypt(api_key_record.encrypted_key)

    def _build_headers(self, api_key: str) -> dict:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _build_messages(self, prompt_zh: str) -> list[dict]:
        return [{"role": "user", "content": prompt_zh}]

    @abstractmethod
    def _build_payload(self, messages: list[dict], model_name: str) -> dict:
        pass

    async def query(
        self,
        prompt_zh: str,
        model_name: Optional[str] = None,
        **kwargs,
    ) -> tuple[str, int, int, float]:
        api_key = self._get_api_key()
        model = model_name or self.default_model
        url = f"{self.api_base}/chat/completions"

        messages = self._build_messages(prompt_zh)
        payload = self._build_payload(messages, model)
        headers = self._build_headers(api_key)

        start_time = time.time()
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                latency = time.time() - start_time
                return self._parse_response(result, latency)
            except httpx.HTTPError as e:
                logger.error(f"{self.provider.value} API error: {e}")
                raise

    def _parse_response(self, result: dict, latency: float) -> tuple[str, int, int, float]:
        answer = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        tokens_in = usage.get("prompt_tokens", 0)
        tokens_out = usage.get("completion_tokens", 0)
        return answer, tokens_in, tokens_out, latency
