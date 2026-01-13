import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a product feature extraction specialist. Given an evidence snippet about a brand/product, extract the specific product features being discussed.

For each feature found, provide:
1. feature_zh: The feature name in Chinese (e.g., "油耗", "空间", "安全性", "价格")
2. feature_en: The feature name in English (e.g., "fuel consumption", "space", "safety", "price")
3. sentiment: The sentiment expressed about this feature - "positive", "neutral", or "negative"

Return a JSON array. If no features found, return empty array: []

Examples:
Input: "奔驰GLE的油耗表现非常出色"
Output: [{"feature_zh": "油耗", "feature_en": "fuel consumption", "sentiment": "positive"}]

Input: "宝马X5空间大但价格偏高"
Output: [{"feature_zh": "空间", "feature_en": "space", "sentiment": "positive"}, {"feature_zh": "价格", "feature_en": "price", "sentiment": "negative"}]

Input: "这是一款SUV"
Output: []"""


def _build_extraction_prompt(
    snippet: str,
    brand_name: Optional[str] = None,
    product_name: Optional[str] = None
) -> str:
    context = ""
    if brand_name:
        context = f"Brand: {brand_name}\n"
    if product_name:
        context += f"Product: {product_name}\n"

    return f"""{context}Extract product features from the following snippet:

{snippet}

Return JSON array only:"""


def _validate_feature_data(data: dict) -> bool:
    if not isinstance(data, dict):
        return False
    feature_zh = data.get("feature_zh", "")
    if not feature_zh or not isinstance(feature_zh, str):
        return False
    return True


def _normalize_sentiment(sentiment: Optional[str]) -> str:
    if not sentiment:
        return "neutral"
    sentiment_lower = sentiment.lower().strip()
    if sentiment_lower in ("positive", "neutral", "negative"):
        return sentiment_lower
    return "neutral"


def _parse_features_response(response: str) -> list[dict]:
    response = response.strip()
    if not response:
        return []

    try:
        start_idx = response.find("[")
        end_idx = response.rfind("]")
        if start_idx == -1 or end_idx == -1:
            return []

        json_str = response[start_idx:end_idx + 1]
        features = json.loads(json_str)

        if not isinstance(features, list):
            return []

        valid_features = []
        for f in features:
            if _validate_feature_data(f):
                f["sentiment"] = _normalize_sentiment(f.get("sentiment"))
                valid_features.append(f)

        return valid_features
    except json.JSONDecodeError:
        logger.warning(f"Failed to parse features JSON: {response[:100]}")
        return []


async def extract_features_from_snippet(
    snippet: str,
    ollama_service,
    brand_name: Optional[str] = None,
    product_name: Optional[str] = None,
) -> list[dict]:
    if not snippet or not snippet.strip():
        return []

    prompt = _build_extraction_prompt(snippet, brand_name, product_name)

    try:
        response = await ollama_service._call_ollama(
            model=ollama_service.ner_model,
            prompt=prompt,
            system_prompt=SYSTEM_PROMPT,
            temperature=0.1,
        )
        return _parse_features_response(response)
    except Exception as e:
        logger.error(f"Feature extraction failed: {e}")
        return []


async def extract_features_batch(
    snippets: list[str],
    ollama_service,
    brand_name: Optional[str] = None,
    product_name: Optional[str] = None,
) -> list[list[dict]]:
    results = []
    for snippet in snippets:
        features = await extract_features_from_snippet(
            snippet, ollama_service, brand_name, product_name
        )
        results.append(features)
    return results


async def extract_features_for_mention(
    evidence_snippets: dict,
    ollama_service,
    brand_name: Optional[str] = None,
    product_name: Optional[str] = None,
) -> list[dict]:
    zh_snippets = evidence_snippets.get("zh", [])
    if not zh_snippets:
        return []

    all_features = []
    seen_features = set()

    for snippet in zh_snippets:
        features = await extract_features_from_snippet(
            snippet, ollama_service, brand_name, product_name
        )
        for f in features:
            key = f["feature_zh"]
            if key not in seen_features:
                seen_features.add(key)
                all_features.append(f)

    return all_features
