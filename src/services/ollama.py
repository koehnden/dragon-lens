import logging
from typing import Optional

import httpx

from config import settings
from services.sentiment_analysis import ErlangshenSentimentService
from services.brand_recognition import (
    is_list_format,
    split_into_list_items,
    extract_snippet_with_list_awareness,
)

logger = logging.getLogger(__name__)

class OllamaService:
    def __init__(self):
        self.base_url = settings.ollama_base_url
        self.translation_model = settings.ollama_model_translation
        self.sentiment_model = settings.ollama_model_sentiment
        self.ner_model = settings.ollama_model_ner
        self.main_model = settings.ollama_model_main

        self.sentiment_service = ErlangshenSentimentService()

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
        if settings.use_erlangshen_sentiment:
            try:
                sentiment = self.sentiment_service.classify_sentiment(text_zh)
                logger.debug(f"Erlangshen sentiment analysis: {text_zh[:50]}... -> {sentiment}")
                return sentiment
            except Exception as e:
                logger.error(f"Erlangshen sentiment analysis failed, falling back to Qwen: {e}")
                return await self._classify_sentiment_with_qwen(text_zh)
        else:
            logger.debug("Erlangshen sentiment analysis disabled, using Qwen")
            return await self._classify_sentiment_with_qwen(text_zh)

    async def _classify_sentiment_with_qwen(self, text_zh: str) -> str:
        system_prompt = (
            "You are a sentiment classifier. Analyze the sentiment of the following Chinese text. "
            "Respond with ONLY ONE WORD: positive, neutral, or negative."
        )
        prompt = f"Classify sentiment:\n{text_zh}"

        result = await self._call_ollama(
            model=self.sentiment_model,
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.1,
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

        all_brand_positions = {}
        all_brand_names_lower = set()
        flat_positions: list[tuple[int, int]] = []

        for i, (brand_name, aliases) in enumerate(zip(brand_names, brand_aliases)):
            all_names = [brand_name.lower()] + [alias.lower() for alias in aliases]
            all_brand_names_lower.update(all_names)

            for name in all_names:
                start_pos = 0
                while True:
                    pos = text_lower.find(name, start_pos)
                    if pos == -1:
                        break
                    if i not in all_brand_positions:
                        all_brand_positions[i] = []
                    all_brand_positions[i].append({
                        'name': name,
                        'start': pos,
                        'end': pos + len(name),
                        'original_name': brand_name
                    })
                    flat_positions.append((pos, pos + len(name)))
                    start_pos = pos + 1

        flat_positions.sort(key=lambda x: x[0])

        for brand_idx, positions in all_brand_positions.items():
            brand_name = brand_names[brand_idx]
            aliases = brand_aliases[brand_idx]
            all_names = [brand_name.lower()] + [alias.lower() for alias in aliases]

            clean_snippets = []
            rank = None

            for pos_info in positions:
                snippet = extract_snippet_with_list_awareness(
                    text_zh,
                    pos_info['start'],
                    pos_info['end'],
                    flat_positions,
                    all_names,
                    max_length=50,
                )

                clean_snippet = snippet
                for other_idx, other_positions in all_brand_positions.items():
                    if other_idx != brand_idx:
                        for other_pos in other_positions:
                            other_name = text_zh[other_pos['start']:other_pos['end']]
                            clean_snippet = clean_snippet.replace(other_name, '[BRAND]')

                clean_snippets.append(clean_snippet)

                prefix = text_zh[max(0, pos_info['start'] - 20):pos_info['start']]
                for num in range(1, 21):
                    if f"{num}." in prefix or f"{num}、" in prefix:
                        rank = num
                        break

            if brand_idx not in all_brand_positions:
                clean_snippets = []
                rank = None

            mentions.append({
                "brand_index": brand_idx,
                "mentioned": len(clean_snippets) > 0,
                "snippets": clean_snippets,
                "rank": rank,
            })

        for i, (brand_name, aliases) in enumerate(zip(brand_names, brand_aliases)):
            if i not in all_brand_positions:
                mentions.append({
                    "brand_index": i,
                    "mentioned": False,
                    "snippets": [],
                    "rank": None,
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
