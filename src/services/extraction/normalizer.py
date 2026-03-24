"""Entity normalization helpers: alias resolution, parenthetical parsing, JSON extraction."""

from __future__ import annotations

import json
import re
from typing import Any

from services.knowledge_verticals import normalize_entity_key

PARENTHETICAL_PATTERN = re.compile(r'^(.+?)\s*[（(](.+?)[）)]$')
LATIN_START_PATTERN = re.compile(r'^[A-Za-z]')
POSSESSIVE_PATTERN = re.compile(r"[''']s$")
MARKDOWN_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", flags=re.DOTALL)


def strip_possessive(name: str) -> str:
    return POSSESSIVE_PATTERN.sub("", name.strip())


def ensure_str(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, list):
        return value[0] if value else None
    return str(value)


def has_collisions(alias_map: dict[str, str]) -> bool:
    grouped: dict[str, int] = {}
    for canonical in alias_map.values():
        grouped[canonical] = grouped.get(canonical, 0) + 1
    return any(count > 1 for count in grouped.values())


def extract_parenthetical_aliases(entities: list[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for entity in entities:
        alias_key, canonical = _parse_single_parenthetical(entity)
        if alias_key and canonical:
            aliases[alias_key] = canonical
    return aliases


def _parse_single_parenthetical(entity: str) -> tuple[str | None, str | None]:
    match = PARENTHETICAL_PATTERN.match(entity.strip())
    if not match:
        return None, None
    outside, inside = match.group(1).strip(), match.group(2).strip()
    if not outside or not inside:
        return None, None
    return _resolve_latin_cjk_pair(outside, inside)


def _resolve_latin_cjk_pair(
    outside: str,
    inside: str,
) -> tuple[str | None, str | None]:
    outside_latin = bool(LATIN_START_PATTERN.match(outside))
    inside_latin = bool(LATIN_START_PATTERN.match(inside))
    if outside_latin and not inside_latin:
        return normalize_entity_key(inside), outside
    if inside_latin and not outside_latin:
        return normalize_entity_key(outside), inside
    return None, None


def apply_parenthetical_aliases(
    normalized: dict[str, str],
    entities: list[str],
) -> dict[str, str]:
    paren_aliases = extract_parenthetical_aliases(entities)
    if not paren_aliases:
        return normalized
    updated = dict(normalized)
    for entity, canonical in updated.items():
        alias_key = normalize_entity_key(canonical)
        if alias_key in paren_aliases:
            updated[entity] = paren_aliases[alias_key]
    return updated


def parse_json_response(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    fenced_match = MARKDOWN_FENCE_PATTERN.match(text)
    if fenced_match:
        text = fenced_match.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return _extract_json_object(text)


def _extract_json_object(text: str) -> dict[str, Any] | None:
    start = text.find("{")
    end = text.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None
