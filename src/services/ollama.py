import logging
from typing import Optional

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class OllamaService:
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.translation_model = settings.ollama_model_translation
        self.sentiment_model = settings.ollama_model_sentiment
        self.ner_model = settings.ollama_model_ner
        self.main_model = settings.ollama_model_main

    async def _call_ollama(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
    ) -> str:
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            }
        }

        if system_prompt:
            payload["system"] = system_prompt

        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                return result.get("response", "")
            except httpx.HTTPError as e:
                logger.error(f"Ollama API error: {e}")
                raise

    async def translate_to_chinese(self, text_en: str) -> str:
        system_prompt = (
            "You are a professional translator. Translate the following English text to Chinese. "
            "Only output the Chinese translation, no explanations."
        )
        prompt = f"Translate to Chinese:\n{text_en}"

        return await self._call_ollama(
            model=self.translation_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,  # Lower temperature for more deterministic translation
        )

    async def translate_to_english(self, text_zh: str) -> str:
        system_prompt = (
            "You are a professional translator. Translate the following Chinese text to English. "
            "Only output the English translation, no explanations."
        )
        prompt = f"Translate to English:\n{text_zh}"

        return await self._call_ollama(
            model=self.translation_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
        )

    async def classify_sentiment(self, text_zh: str) -> str:
        system_prompt = (
            "You are a sentiment classifier. Analyze the sentiment of the following Chinese text. "
            "Respond with ONLY ONE WORD: positive, neutral, or negative."
        )
        prompt = f"Classify sentiment:\n{text_zh}"

        result = await self._call_ollama(
            model=self.sentiment_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,  # Very low temperature for classification
        )

        result = result.strip().lower()
        if "positive" in result:
            return "positive"
        elif "negative" in result:
            return "negative"
        else:
            return "neutral"

    async def query_main_model(self, prompt_zh: str) -> tuple[str, int, int]:
        response = await self._call_ollama(
            model=self.main_model,
            prompt=prompt_zh,
            temperature=0.7,
        )

        tokens_in = len(prompt_zh) // 2
        tokens_out = len(response) // 2

        return response, tokens_in, tokens_out

    async def extract_brands(
        self,
        text_zh: str,
        brand_names: list[str],
        brand_aliases: list[list[str]],
    ) -> list[dict]:
        mentions = []
        text_lower = text_zh.lower()

        for i, (brand_name, aliases) in enumerate(zip(brand_names, brand_aliases)):
            all_names = [brand_name.lower()] + [alias.lower() for alias in aliases]
            found = False
            snippets = []
            rank = None

            for name in all_names:
                if name in text_lower:
                    found = True
                    pos = text_lower.index(name)
                    start = max(0, pos - 50)
                    end = min(len(text_zh), pos + len(name) + 50)
                    snippet = text_zh[start:end]
                    snippets.append(snippet)

            if found:
                for name in all_names:
                    if name in text_lower:
                        pos = text_lower.index(name)
                        prefix = text_zh[max(0, pos - 20):pos]
                        for num in range(1, 21):  # Check ranks 1-20
                            if f"{num}." in prefix or f"{num}、" in prefix:
                                rank = num
                                break
                        break

            mentions.append({
                "brand_index": i,
                "mentioned": found,
                "snippets": snippets,
                "rank": rank,
            })

        return mentions

    async def check_health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False
