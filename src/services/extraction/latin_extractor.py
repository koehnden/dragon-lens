"""Extract Latin-alphabet tokens from Chinese text as brand/product candidates."""

from __future__ import annotations

import re

LATIN_WORD_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[-'][A-Za-z0-9]+)*")

STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "for", "in", "on", "to", "with",
    "is", "are", "was", "were", "it", "its", "this", "that", "by", "from",
    "vs", "etc", "eg", "ie", "no", "not", "but", "so", "if", "at", "as",
    "kg", "cm", "mm", "ml", "gb", "tb", "hz", "rpm",
    "ok", "hi", "yes", "go", "up", "do", "be", "he", "we", "me",
    "app", "http", "https", "www", "com", "cn", "org",
})

CJK_PATTERN = re.compile(r"[\u4e00-\u9fff]")
LATIN_CHAR_PATTERN = re.compile(r"[A-Za-z]")
MIN_TOKEN_LENGTH = 2
MIN_CJK_RATIO = 0.15


def is_cjk_dominant(text: str) -> bool:
    if not text:
        return False
    non_space = re.sub(r"\s", "", text)
    if not non_space:
        return False
    cjk_count = len(CJK_PATTERN.findall(non_space))
    return cjk_count / len(non_space) >= MIN_CJK_RATIO


def extract_latin_tokens(text: str) -> list[str]:
    if not is_cjk_dominant(text):
        return []
    raw_matches = LATIN_WORD_PATTERN.findall(text)
    seen: set[str] = set()
    tokens: list[str] = []
    for match in raw_matches:
        cleaned = match.strip()
        if len(cleaned) < MIN_TOKEN_LENGTH:
            continue
        if cleaned.lower() in STOPWORDS:
            continue
        if _is_size_or_number(cleaned):
            continue
        lower = cleaned.lower()
        if lower in seen:
            continue
        seen.add(lower)
        tokens.append(cleaned)
    return tokens


def _is_size_or_number(token: str) -> bool:
    if re.fullmatch(r"[0-9]+", token):
        return True
    if re.fullmatch(r"[SMLX]{1,3}L?", token, re.IGNORECASE):
        return True
    if re.fullmatch(r"[0-9]+[A-Za-z]{1,2}", token):
        return True
    return False
