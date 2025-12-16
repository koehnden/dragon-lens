import logging
from typing import Optional

import httpx

from config import settings

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

        timeout = httpx.Timeout(
            connect=10.0,
            read=600.0,
            write=10.0,
            pool=10.0
        )

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                result = response.json()
                return result.get("response", "")
            except httpx.HTTPError as e:
                logger.error(f"Ollama API error: {e}")
                raise

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

    async def get_embeddings(self, texts: list[str], model: str = "bge-small-zh-v1.5") -> list[list[float]]:
        url = f"{self.base_url}/api/embeddings"

        embeddings = []
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            for text in texts:
                payload = {"model": model, "prompt": text}
                try:
                    response = await client.post(url, json=payload)
                    response.raise_for_status()
                    result = response.json()
                    embeddings.append(result.get("embedding", []))
                except httpx.HTTPError as e:
                    logger.error(f"Ollama embeddings API error for text '{text[:50]}': {e}")
                    raise

        return embeddings

    async def check_health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Ollama health check failed: {e}")
            return False
