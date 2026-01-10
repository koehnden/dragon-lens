from __future__ import annotations

import json


def parse_comparison_prompts_from_text(text: str) -> list[dict]:
    payload = _json_array_substring(text)
    items = _parse_json_list(payload)
    return _prompt_dicts(items)


def _json_array_substring(text: str) -> str:
    raw = (text or "").strip()
    start = raw.find("[")
    end = raw.rfind("]")
    if start < 0 or end < 0 or end <= start:
        return ""
    return raw[start : end + 1]


def _parse_json_list(payload: str) -> list:
    if not payload:
        return []
    try:
        data = json.loads(payload)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _prompt_dicts(items: list) -> list[dict]:
    if not items:
        return []
    out: list[dict] = []
    for item in items:
        normalized = _normalized_prompt(item)
        if normalized:
            out.append(normalized)
    return out


def _normalized_prompt(item: object) -> dict | None:
    if not isinstance(item, dict):
        return None
    zh = (item.get("text_zh") or "").strip()
    en = (item.get("text_en") or "").strip()
    if not zh or not en:
        return None
    prompt_type = (item.get("prompt_type") or "brand_vs_brand").strip()
    if prompt_type not in {"brand_vs_brand", "product_vs_product"}:
        return None
    aspects = item.get("aspects")
    return {
        "text_zh": zh,
        "text_en": en,
        "prompt_type": prompt_type,
        "primary_brand": (item.get("primary_brand") or "").strip(),
        "competitor_brand": (item.get("competitor_brand") or "").strip(),
        "primary_product": (item.get("primary_product") or "").strip(),
        "competitor_product": (item.get("competitor_product") or "").strip(),
        "aspects": aspects if isinstance(aspects, list) else [],
    }
