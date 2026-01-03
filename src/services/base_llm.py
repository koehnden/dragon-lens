import logging
import time
from abc import ABC, abstractmethod
from typing import Optional

import httpx
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from config import settings
from models import APIKey
from models.domain import LLMProvider
from services.encryption import EncryptionService

logger = logging.getLogger(__name__)

ENV_API_KEYS = {
    LLMProvider.DEEPSEEK: lambda: settings.deepseek_api_key,
    LLMProvider.KIMI: lambda: settings.kimi_api_key,
}


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

        env_key_getter = ENV_API_KEYS.get(self.provider)
        if env_key_getter:
            env_key = env_key_getter()
            if env_key:
                return env_key

        if self.db:
            api_key_record = (
                self.db.query(APIKey)
                .filter(
                    APIKey.provider == self.provider.value,
                    APIKey.is_active == True,
                )
                .first()
            )
            if api_key_record:
                return self._get_encryption_service().decrypt(api_key_record.encrypted_key)

        raise ValueError(f"No active {self.provider.value} API key found")

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


class OpenAICompatibleService(BaseLLMService):
    provider: LLMProvider
    default_model: str
    api_base: str
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    system_prompt: Optional[str] = None

    def _build_payload(self, messages: list[dict], model_name: str) -> dict:
        return {"model": model_name, "messages": messages}

    def _build_messages(self, prompt_zh: str) -> list[dict]:
        messages = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.append({"role": "user", "content": prompt_zh})
        return messages

    async def query(
        self,
        prompt_zh: str,
        model_name: Optional[str] = None,
        **kwargs,
    ) -> tuple[str, int, int, float]:
        api_key = self._get_api_key()
        model = model_name or self.default_model

        client = AsyncOpenAI(api_key=api_key, base_url=self.api_base)

        messages = self._build_messages(prompt_zh)
        request_kwargs = {"model": model, "messages": messages}

        if self.temperature is not None:
            request_kwargs["temperature"] = self.temperature
        if self.max_tokens is not None:
            request_kwargs["max_tokens"] = self.max_tokens

        start_time = time.time()
        try:
            response = await client.chat.completions.create(**request_kwargs)
            latency = time.time() - start_time
            return self._parse_openai_response(response, latency)
        except Exception as e:
            logger.error(f"{self.provider.value} API error: {e}")
            raise

    def _parse_openai_response(self, response, latency: float) -> tuple[str, int, int, float]:
        answer = response.choices[0].message.content
        tokens_in = response.usage.prompt_tokens if response.usage else 0
        tokens_out = response.usage.completion_tokens if response.usage else 0
        return answer, tokens_in, tokens_out, latency
