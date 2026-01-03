"""
Text normalization and preprocessing utilities.

This module contains functions for normalizing text for NER processing,
including character conversion, punctuation normalization, and whitespace handling.
"""

import re
import unicodedata

import importlib


def normalize_text_for_ner(text: str) -> str:
    """Normalize text for NER processing."""
    if not text:
        return text

    normalized = text

    fullwidth_to_halfwidth = {
        '０': '0', '１': '1', '２': '2', '３': '3', '４': '4',
        '５': '5', '６': '6', '７': '7', '８': '8', '９': '9',
        'Ａ': 'A', 'Ｂ': 'B', 'Ｃ': 'C', 'Ｄ': 'D', 'Ｅ': 'E',
        'Ｆ': 'F', 'Ｇ': 'G', 'Ｈ': 'H', 'Ｉ': 'I', 'Ｊ': 'J',
        'Ｋ': 'K', 'Ｌ': 'L', 'Ｍ': 'M', 'Ｎ': 'N', 'Ｏ': 'O',
        'Ｐ': 'P', 'Ｑ': 'Q', 'Ｒ': 'R', 'Ｓ': 'S', 'Ｔ': 'T',
        'Ｕ': 'U', 'Ｖ': 'V', 'Ｗ': 'W', 'Ｘ': 'X', 'Ｙ': 'Y',
        'Ｚ': 'Z',
        'ａ': 'a', 'ｂ': 'b', 'ｃ': 'c', 'ｄ': 'd', 'ｅ': 'e',
        'ｆ': 'f', 'ｇ': 'g', 'ｈ': 'h', 'ｉ': 'i', 'ｊ': 'j',
        'ｋ': 'k', 'ｌ': 'l', 'ｍ': 'm', 'ｎ': 'n', 'ｏ': 'o',
        'ｐ': 'p', 'ｑ': 'q', 'ｒ': 'r', 'ｓ': 's', 'ｔ': 't',
        'ｕ': 'u', 'ｖ': 'v', 'ｗ': 'w', 'ｘ': 'x', 'ｙ': 'y',
        'ｚ': 'z',
        '　': ' ', '（': '(', '）': ')', '［': '[', '］': ']',
        '｛': '{', '｝': '}', '＜': '<', '＞': '>',
        '＋': '+', '－': '-', '＝': '=', '＊': '*', '／': '/',
        '＆': '&', '％': '%', '＄': '$', '＃': '#', '＠': '@',
        '！': '!', '？': '?', '．': '.', '，': ',', '：': ':',
        '；': ';', '｜': '|', '～': '~', '＿': '_',
    }

    for fullwidth, halfwidth in fullwidth_to_halfwidth.items():
        normalized = normalized.replace(fullwidth, halfwidth)

    chinese_punct_map = {
        '，': ',', '。': '.', '！': '!', '？': '?',
        '：': ':', '；': ';', '、': ',',
        '"': '"', '"': '"', ''': "'", ''': "'",
        '「': '"', '」': '"', '『': '"', '』': '"',
        '【': '[', '】': ']', '《': '<', '》': '>',
        '—': '-', '…': '...',
    }

    for chinese_punct, ascii_punct in chinese_punct_map.items():
        normalized = normalized.replace(chinese_punct, ascii_punct)

    normalized = normalized.replace('\u3000', ' ')
    normalized = normalized.replace('\xa0', ' ')

    normalized = ' '.join(normalized.split())

    return normalized


def _normalize_text(value: str) -> str:
    """Normalize text for comparison (lowercase, remove spaces/punctuation)."""
    simplified = _convert_to_simplified(value)
    folded = unicodedata.normalize("NFKC", simplified).lower()
    stripped = re.sub(r"[\s\W·•\-_/]+", "", folded)
    return stripped


def _convert_to_simplified(value: str) -> str:
    """Convert traditional Chinese to simplified Chinese if opencc is available."""
    converter = _load_optional_model("opencc", "OpenCC")
    if not converter:
        return value
    try:
        return converter("t2s").convert(value)
    except Exception:
        return value


def _load_optional_model(module_name: str, attr: str):
    """Load an optional module if available."""
    module = importlib.util.find_spec(module_name)
    if not module:
        return None
    module_obj = importlib.import_module(module_name)
    return getattr(module_obj, attr, None)


def extract_snippet_for_brand(
    text: str,
    brand_start: int,
    brand_end: int,
    all_brand_positions: list,
    max_length: int = 50,
) -> str:
    """Extract a snippet of text containing a brand mention."""
    if not text:
        return ""

    snippet_start = brand_start
    snippet_end = min(len(text), brand_end + max_length)

    for other_start, other_end in all_brand_positions:
        if other_start > brand_end and other_start < snippet_end:
            snippet_end = other_start
            break

    return text[snippet_start:snippet_end].strip()


def extract_snippet_with_list_awareness(
    text: str,
    brand_start: int,
    brand_end: int,
    all_brand_positions: list,
    brand_names_lower: list,
    max_length: int = 50,
) -> str:
    """Extract a snippet with awareness of list formatting."""
    from services.brand_recognition.list_processor import is_list_format, split_into_list_items

    if is_list_format(text):
        list_items = split_into_list_items(text)
        list_items_lower = [item.lower() for item in list_items]
        for i, item_lower in enumerate(list_items_lower):
            for name in brand_names_lower:
                if name in item_lower:
                    return list_items[i]

    return extract_snippet_for_brand(
        text, brand_start, brand_end, all_brand_positions, max_length
    )


def _build_alias_lookup(
    primary_brand: str,
    aliases: dict,
    alias_table: dict
) -> dict:
    """Build a lookup table for normalizing brand names to canonical forms."""
    lookup = {}
    canonical_primary = _normalize_text(primary_brand) if primary_brand else ""

    if canonical_primary:
        lookup[canonical_primary] = canonical_primary

    for alias_list in aliases.values():
        for alias in alias_list:
            normalized = _normalize_text(alias)
            if normalized:
                lookup[normalized] = canonical_primary

    for alias, canonical in alias_table.items():
        normalized_alias = _normalize_text(alias)
        normalized_canonical = _normalize_text(canonical)
        if normalized_alias and normalized_canonical:
            lookup[normalized_alias] = normalized_canonical

    return lookup


def _has_variant_signals(text: str) -> bool:
    """Check if text contains variant signals (model numbers, suffixes, etc.)."""
    if not text or len(text) < 2:
        return False

    text_lower = text.lower()

    if re.search(r'\d', text):
        return True

    trim_markers = [
        'pro', 'max', 'plus', 'ultra', 'mini',
        'dm-i', 'dm-p', 'ev', 'phev', 'bev',
        'sport', 'luxury', 'premium', 'elite',
        'performance'
    ]
    if any(marker in text_lower for marker in trim_markers):
        return True

    if 'longrange' in text_lower or 'long range' in text_lower:
        return True
    if 'standardrange' in text_lower or 'standard range' in text_lower:
        return True

    capacity_size_patterns = [
        r'\d+\s*[gt]b?',
        r'\d+\s*英寸',
        r'\d+\s*寸',
        r'\d+\.?\d*\s*[lt]',
        r'\d+\s*mah',
        r'\d+\s*w',
    ]
    if any(re.search(pattern, text_lower) for pattern in capacity_size_patterns):
        return True

    return False


def _match_substring_alias(normalized: str, lookup: dict) -> str | None:
    """Match a normalized string against alias lookup, respecting variant constraints."""
    import logging
    logger = logging.getLogger(__name__)

    for alias_norm, canonical in lookup.items():
        if not alias_norm or alias_norm not in normalized:
            continue

        if alias_norm == normalized:
            return canonical

        if _has_variant_signals(normalized) and not _has_variant_signals(alias_norm):
            logger.debug(f"Merge constraint: '{normalized}' has variant signals, '{alias_norm}' doesn't - skipping merge")
            continue

        if len(normalized) > len(alias_norm):
            suffix = normalized[len(alias_norm):]
            if _has_variant_signals(suffix):
                logger.debug(f"Merge constraint: suffix '{suffix}' of '{normalized}' has variant signals - skipping merge")
                continue

        logger.debug(f"Allowing merge: '{normalized}' -> '{canonical}' via alias '{alias_norm}'")
        return canonical

    return None


def _extract_evidence(name: str, text: str, context_chars: int = 50) -> dict | None:
    """Extract evidence of a brand/product mention from text."""
    name_lower = name.lower()
    text_lower = text.lower()

    start_pos = text_lower.find(name_lower)
    if start_pos == -1:
        return None

    end_pos = start_pos + len(name)

    snippet_start = max(0, start_pos - context_chars)
    snippet_end = min(len(text), end_pos + context_chars)

    snippet = text[snippet_start:snippet_end]

    if snippet_start > 0:
        snippet = "..." + snippet
    if snippet_end < len(text):
        snippet = snippet + "..."

    return {
        "snippet": snippet,
        "start": start_pos,
        "end": end_pos,
        "mention": text[start_pos:end_pos]
    }


def _parse_json_response(response: str) -> dict | None:
    """Parse a JSON response from Qwen."""
    import json

    response = response.strip()

    if response.startswith("```json"):
        response = response[7:]
    if response.startswith("```"):
        response = response[3:]
    if response.endswith("```"):
        response = response[:-3]
    response = response.strip()

    try:
        return json.loads(response)
    except json.JSONDecodeError:
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

    return None
