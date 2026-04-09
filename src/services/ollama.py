import asyncio
import logging
import re
import time
from typing import Optional

import httpx

from config import settings
from services.brand_recognition import extract_snippet_with_list_awareness
from services.mention_ranking import rank_entities
from services.sentiment_analysis import get_sentiment_service

logger = logging.getLogger(__name__)


class OllamaOverloadedError(httpx.HTTPStatusError):
    """Raised when Ollama returns 503 (overloaded/busy)."""


_RETRYABLE_EXCEPTIONS = (
    httpx.ReadTimeout,
    httpx.ConnectTimeout,
    httpx.ConnectError,
    OllamaOverloadedError,
)


class OllamaService:
    _shared_client: Optional[httpx.AsyncClient] = None
    _client_loop: Optional[asyncio.AbstractEventLoop] = None

    def __init__(self) -> None:
        self.base_url = settings.ollama_base_url
        self.translation_model = settings.ollama_model_translation
        self.sentiment_model = settings.ollama_model_sentiment
        self.ner_model = settings.ollama_model_ner
        self.main_model = settings.ollama_model_main

        self._sentiment_service = None

    @classmethod
    def _get_client(cls) -> httpx.AsyncClient:
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        loop_changed = current_loop is not None and current_loop is not cls._client_loop
        if cls._shared_client is not None and (cls._shared_client.is_closed or loop_changed):
            cls._shared_client = None

        if cls._shared_client is None:
            timeout = httpx.Timeout(
                connect=10.0,
                read=settings.ollama_read_timeout,
                write=10.0,
                pool=10.0,
            )
            cls._shared_client = httpx.AsyncClient(timeout=timeout)
            cls._client_loop = current_loop
        return cls._shared_client

    @classmethod
    async def close_client(cls) -> None:
        if cls._shared_client is not None and not cls._shared_client.is_closed:
            await cls._shared_client.aclose()
            cls._shared_client = None
            cls._client_loop = None

    def _get_sentiment_service(self):
        if self._sentiment_service is None:
            self._sentiment_service = get_sentiment_service()
        return self._sentiment_service

    async def _call_ollama(
        self,
        model: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        format: Optional[str] = None,
    ) -> str:
        url = f"{self.base_url}/api/chat"

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict = {
            "model": model,
            "messages": messages,
            "stream": False,
            "think": False,
            "keep_alive": settings.ollama_keep_alive,
            "options": {
                "temperature": temperature,
            },
        }
        if format:
            payload["format"] = format

        client = self._get_client()
        last_exc: Exception | None = None
        for attempt in range(settings.ollama_retry_attempts):
            try:
                response = await client.post(url, json=payload)
                if response.status_code == 503:
                    raise OllamaOverloadedError(
                        "Ollama overloaded (503)",
                        request=response.request,
                        response=response,
                    )
                response.raise_for_status()
                result = response.json()
                return result.get("message", {}).get("content", "")
            except _RETRYABLE_EXCEPTIONS as exc:
                last_exc = exc
                if attempt < settings.ollama_retry_attempts - 1:
                    delay = settings.ollama_retry_base_delay * (2 ** attempt)
                    logger.warning(
                        "Ollama call failed (attempt %d/%d, model=%s): %s — retrying in %.1fs",
                        attempt + 1, settings.ollama_retry_attempts, model, exc, delay,
                    )
                    await asyncio.sleep(delay)
            except httpx.HTTPError as exc:
                logger.error("Ollama API error (model=%s): %s", model, exc)
                raise

        logger.error(
            "Ollama call failed after %d attempts (model=%s): %s",
            settings.ollama_retry_attempts, model, last_exc,
        )
        raise last_exc  # type: ignore[misc]

    async def classify_sentiment(self, text_zh: str) -> str:
        if settings.use_erlangshen_sentiment:
            try:
                sentiment = self._get_sentiment_service().classify_sentiment(text_zh)
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

    async def query_main_model(self, prompt_zh: str, model_name: Optional[str] = None) -> tuple[str, int, int, float]:
        model_to_use = model_name or self.main_model
        start_time = time.time()
        
        response = await self._call_ollama(
            model=model_to_use,
            prompt=prompt_zh,
            temperature=0.7,
        )
        
        latency = time.time() - start_time
        tokens_in = len(prompt_zh) // 2
        tokens_out = len(response) // 2

        return response, tokens_in, tokens_out, latency

    async def extract_brands(
        self,
        text_zh: str,
        brand_names: list[str],
        brand_aliases: list[list[str]],
    ) -> list[dict]:
        return await _extract_mentions(
            text_zh,
            brand_names,
            brand_aliases,
            index_key="brand_index",
            self_mask_token="[BRAND]",
            extra_masks=[],
        )

    async def extract_products(
        self,
        text_zh: str,
        product_names: list[str],
        product_aliases: list[list[str]],
        brand_names: list[str],
        brand_aliases: list[list[str]],
    ) -> list[dict]:
        masks = [("[BRAND]", _flatten_variants(brand_names, brand_aliases))]
        return await _extract_mentions(
            text_zh,
            product_names,
            product_aliases,
            index_key="product_index",
            self_mask_token="[PRODUCT]",
            extra_masks=masks,
        )


def _flatten_variants(names: list[str], aliases: list[list[str]]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for name, alias_list in zip(names, aliases):
        for v in [name] + list(alias_list):
            if not v or v in seen:
                continue
            seen.add(v)
            result.append(v)
    return result


async def _extract_mentions(
    text_zh: str,
    entity_names: list[str],
    entity_aliases: list[list[str]],
    index_key: str,
    self_mask_token: str,
    extra_masks: list[tuple[str, list[str]]],
) -> list[dict]:
    mentions: list[dict] = []
    positions, flat = _find_all_positions(text_zh, entity_names, entity_aliases)
    ranks = rank_entities(text_zh, [[n] + a for n, a in zip(entity_names, entity_aliases)])

    for entity_idx, entity_positions in positions.items():
        variants = [entity_names[entity_idx].lower()] + [a.lower() for a in entity_aliases[entity_idx]]
        snippets = [_snippet_for_position(text_zh, p, flat, variants) for p in entity_positions]
        masked = [_mask_other_entities(s, text_zh, entity_idx, positions, self_mask_token) for s in snippets]
        masked = [_apply_extra_masks(s, extra_masks) for s in masked]
        mentions.append({index_key: entity_idx, "mentioned": bool(masked), "snippets": masked, "rank": ranks[entity_idx]})

    for i in range(len(entity_names)):
        if i not in positions:
            mentions.append({index_key: i, "mentioned": False, "snippets": [], "rank": None})
    return mentions


def _find_all_positions(
    text_zh: str,
    entity_names: list[str],
    entity_aliases: list[list[str]],
) -> tuple[dict[int, list[dict]], list[tuple[int, int]]]:
    text_lower = (text_zh or "").lower()
    positions: dict[int, list[dict]] = {}
    flat: list[tuple[int, int]] = []
    for i, (name, aliases) in enumerate(zip(entity_names, entity_aliases)):
        for v in [name.lower()] + [a.lower() for a in aliases]:
            for start, end in _find_occurrences(text_lower, v):
                positions.setdefault(i, []).append({"start": start, "end": end})
                flat.append((start, end))
    return positions, sorted(flat, key=lambda x: x[0])


def _find_occurrences(text_lower: str, needle: str) -> list[tuple[int, int]]:
    if not needle:
        return []
    hits: list[tuple[int, int]] = []
    start = 0
    while True:
        pos = text_lower.find(needle, start)
        if pos < 0:
            return hits
        hits.append((pos, pos + len(needle)))
        start = pos + 1


def _snippet_for_position(
    text_zh: str,
    pos: dict,
    all_positions: list[tuple[int, int]],
    variants_lower: list[str],
) -> str:
    return extract_snippet_with_list_awareness(
        text_zh,
        pos["start"],
        pos["end"],
        all_positions,
        variants_lower,
        max_length=50,
    )


def _mask_other_entities(
    snippet: str,
    text_zh: str,
    entity_idx: int,
    positions: dict[int, list[dict]],
    token: str,
) -> str:
    masked = snippet
    for other_idx, other_positions in positions.items():
        if other_idx == entity_idx:
            continue
        for p in other_positions:
            masked = masked.replace(text_zh[p["start"]:p["end"]], token)
    return masked


def _apply_extra_masks(snippet: str, masks: list[tuple[str, list[str]]]) -> str:
    masked = snippet
    for token, variants in masks:
        masked = _mask_variants(masked, variants, token)
    return masked


def _mask_variants(text: str, variants: list[str], token: str) -> str:
    if not variants:
        return text
    pattern = "|".join(re.escape(v) for v in sorted(set(variants), key=len, reverse=True) if v)
    return re.sub(pattern, token, text, flags=re.IGNORECASE) if pattern else text
