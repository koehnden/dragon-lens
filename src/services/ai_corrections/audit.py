from __future__ import annotations

import json
import re
from typing import Any

from prompts import load_prompt
from services.canonicalization_metrics import normalize_entity_key


def build_audit_prompt(vertical_name: str, items: list[dict[str, Any]]) -> str:
    items_json = json.dumps(items, ensure_ascii=False)
    return load_prompt("ai_corrections/audit_user_prompt", vertical_name=vertical_name, items_json=items_json)


def parse_audit_response(text: str) -> dict[str, Any]:
    payload = _first_json_object(text)
    data = json.loads(payload)
    return data if isinstance(data, dict) else {}


def _first_json_object(text: str) -> str:
    clean = _strip_fences(text or "")
    match = re.search(r"\{.*\}", clean, flags=re.DOTALL)
    return match.group(0) if match else "{}"


def _strip_fences(text: str) -> str:
    return re.sub(r"^```[a-zA-Z]*\s*|\s*```$", "", (text or "").strip())


def key_set(items: list[str]) -> set[str]:
    return {normalize_entity_key(i) for i in items if (i or "").strip()}


def mapping_key_set(items: list[dict[str, str]]) -> set[tuple[str, str]]:
    pairs = [(i.get("product", ""), i.get("brand", "")) for i in items if i]
    return {(normalize_entity_key(p), normalize_entity_key(b)) for p, b in pairs if p and b}

