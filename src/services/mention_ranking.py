import re
from typing import Iterable, Optional


def rank_entities(text: str, variants_by_entity: list[list[str]]) -> list[Optional[int]]:
    return _rank_entities_by_first_occurrence(text, variants_by_entity)


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


def _cap_rank(rank: int) -> int:
    return rank if rank <= 10 else 10
