import logging
import time
from typing import Optional

import httpx
from sqlalchemy.orm import Session

from config import settings
from src.models import APIKey
from src.services.encryption import EncryptionService

logger = logging.getLogger(__name__)


class DeepSeekService:
    def __init__(self, db: Optional[Session] = None, api_key: Optional[str] = None):
        self.db = db
        self.api_key = api_key
        self.api_base = settings.deepseek_api_base
        self._encryption_service = None

    def _get_encryption_service(self) -> EncryptionService:
        if self._encryption_service is None:
            self._encryption_service = EncryptionService()
        return self._encryption_service

    def _get_api_key(self) -> str:
        if self.api_key:
            return self.api_key

        if not self.db:
            raise ValueError("Database session required when api_key not provided")

        api_key_record = (
            self.db.query(APIKey)
            .filter(
                APIKey.provider == "deepseek",
                APIKey.is_active == True,
            )
            .first()
        )

        if not api_key_record:
            raise ValueError("No active DeepSeek API key found in database")

        encryption_service = self._get_encryption_service()
        return encryption_service.decrypt(api_key_record.encrypted_key)

    async def query(self, prompt_zh: str, model_name: str = "deepseek-chat") -> tuple[str, int, int, float]:
        api_key = self._get_api_key()

        url = f"{self.api_base}/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": model_name,
            "messages": [
                {"role": "user", "content": prompt_zh}
            ],
            "temperature": 0.7,
        }

        start_time = time.time()
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
                result = response.json()
                latency = time.time() - start_time

                answer = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {})
                tokens_in = usage.get("prompt_tokens", 0)
                tokens_out = usage.get("completion_tokens", 0)

                return answer, tokens_in, tokens_out, latency

            except httpx.HTTPError as e:
                logger.error(f"DeepSeek API error: {e}")
                raise


class KimiService:
    def __init__(self, db: Optional[Session] = None, api_key: Optional[str] = None):
        self.db = db
        self.api_key = api_key
        self.api_base = settings.kimi_api_base
        self._encryption_service = None

    def _get_encryption_service(self) -> EncryptionService:
        if self._encryption_service is None:
            self._encryption_service = EncryptionService()
        return self._encryption_service

    def _get_api_key(self) -> str:
        if self.api_key:
            return self.api_key

        if not self.db:
            raise ValueError("Database session required when api_key not provided")

        api_key_record = (
            self.db.query(APIKey)
            .filter(
                APIKey.provider == "kimi",
                APIKey.is_active == True,
            )
            .first()
        )

        if not api_key_record:
            raise ValueError("No active Kimi API key found in database")

        encryption_service = self._get_encryption_service()
        return encryption_service.decrypt(api_key_record.encrypted_key)

    async def query(
        self,
        prompt_zh: str,
        enable_web_search: bool = False,
    ) -> tuple[str, int, int]:
        api_key = self._get_api_key()

        raise NotImplementedError("Kimi integration not yet implemented")


class LLMRouter:
    def __init__(self, db=None):
        from src.services.ollama import OllamaService

        self.db = db
        self.ollama = OllamaService()
        self.deepseek = DeepSeekService(db)
        self.kimi = KimiService(db)

    async def query(
        self,
        provider: str,
        model_name: str,
        prompt_zh: str,
        enable_web_search: bool = False,
    ) -> tuple[str, int, int, float]:
        provider = provider.lower()
        model_name = model_name.lower()

        if provider == "qwen":
            return await self.ollama.query_main_model(prompt_zh, model_name)
        elif provider == "deepseek":
            return await self.deepseek.query(prompt_zh, model_name)
        elif provider == "kimi":
            answer, tokens_in, tokens_out = await self.kimi.query(
                prompt_zh, enable_web_search=enable_web_search
            )
            return answer, tokens_in, tokens_out, 0.0
        else:
            raise ValueError(f"Unsupported provider: {provider}")
