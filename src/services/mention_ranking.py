import re
from typing import Iterable, Optional

from services.brand_recognition import is_list_format, split_into_list_items


def rank_entities(text: str, variants_by_entity: list[list[str]]) -> list[Optional[int]]:
    if is_list_format(text):
        return _rank_entities_in_list(text, variants_by_entity)
    return _rank_entities_by_first_occurrence(text, variants_by_entity)


def _rank_entities_in_list(text: str, variants_by_entity: list[list[str]]) -> list[Optional[int]]:
    intro = _intro_text(text)
    items = split_into_list_items(text)
    return [_rank_in_intro_or_items(intro, items, v) for v in variants_by_entity]


def _rank_in_intro_or_items(intro: str, items: list[str], variants: list[str]) -> Optional[int]:
    if _contains_any(intro, variants):
        return 1
    for i, item in enumerate(items):
        if _contains_any(item, variants):
            return _cap_rank(i + 1)
    return None


def _rank_entities_by_first_occurrence(text: str, variants_by_entity: list[list[str]]) -> list[Optional[int]]:
    matches = [_best_match(text, v) for v in variants_by_entity]
    order = [(m, i) for i, m in enumerate(matches) if m is not None]
    ranks: list[Optional[int]] = [None] * len(variants_by_entity)
    for r, (_, i) in enumerate(sorted(order), start=1):
        ranks[i] = _cap_rank(r)
    return ranks


def _best_match(text: str, variants: Iterable[str]) -> Optional[tuple[int, int]]:
    haystack = _norm(text)
    candidates = [_match_candidate(haystack, v) for v in variants]
    found = [c for c in candidates if c is not None]
    return min(found) if found else None


def _match_candidate(haystack: str, variant: str) -> Optional[tuple[int, int]]:
    needle = _norm(variant).strip()
    if not needle:
        return None
    pos = haystack.find(needle)
    return (pos, -len(needle)) if pos >= 0 else None


def _norm(text: str) -> str:
    return (text or "").casefold()


def _contains_any(text: str, variants: Iterable[str]) -> bool:
    haystack = (text or "").casefold()
    for v in variants:
        needle = (v or "").strip().casefold()
        if needle and needle in haystack:
            return True
    return False


def _cap_rank(rank: int) -> int:
    return rank if rank <= 10 else 10


def _intro_text(text: str) -> str:
    idx = _first_list_marker_index(text)
    return text[:idx].strip() if idx > 0 else ""


def _first_list_marker_index(text: str) -> int:
    pattern = r"(?:^\s*\d+[.\)]|^\s*\d+、|^\s*[-*]|^\s*[・○→]|^#{1,4}\s*\**\d+[.\)])"
    match = re.search(pattern, text or "", flags=re.MULTILINE)
    return match.start() if match else 0
