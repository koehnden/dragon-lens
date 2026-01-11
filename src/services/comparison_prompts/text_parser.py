from __future__ import annotations

import json


def parse_text_zh_list_from_text(text: str) -> list[str]:
    items = _parse_json_list(_json_array_substring(text))
    return [_text_zh(i) for i in items if _text_zh(i)]


def _text_zh(item: object) -> str:
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        return str(item.get("text_zh") or "").strip()
    return ""


def _json_array_substring(text: str) -> str:
    raw = (text or "").strip()
    start, end = raw.find("["), raw.rfind("]")
    return raw[start : end + 1] if start >= 0 and end > start else ""


def _parse_json_list(payload: str) -> list:
    if not payload:
        return []
    try:
        parsed = json.loads(payload)
    except Exception:
        return []
    return parsed if isinstance(parsed, list) else []

