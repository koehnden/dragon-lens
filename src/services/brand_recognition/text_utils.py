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
