from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from models.domain import EntityType
from models.knowledge_domain import (
    KnowledgeRejectedEntity,
    KnowledgeTranslationOverride,
    KnowledgeVertical,
)

DEFAULT_EXAMPLE_LIMIT = 30
DEFAULT_MAX_PER_OTHER_VERTICAL = 3

_BORING_REASONS = {"", "user_reject", "user_rejected"}


@dataclass(frozen=True)
class _RejectedCandidate:
    vertical_id: int
    vertical_name: str
    name: str
    reason: str
    created_at: datetime


@dataclass(frozen=True)
class _TranslationCandidate:
    vertical_id: int
    vertical_name: str
    canonical_name: str
    override_text: str
    reason: str | None
    created_at: datetime


def rejected_examples(
    db: Session,
    target_vertical_id: int | None,
    entity_type: EntityType,
    limit: int = DEFAULT_EXAMPLE_LIMIT,
    max_per_other_vertical: int = DEFAULT_MAX_PER_OTHER_VERTICAL,
) -> list[dict]:
    rows = _rejected_candidates(db, entity_type)
    return _select_diverse(rows, target_vertical_id, limit, max_per_other_vertical, _rejected_payload)


def translation_override_examples(
    db: Session,
    target_vertical_id: int | None,
    entity_type: EntityType,
    limit: int = DEFAULT_EXAMPLE_LIMIT,
    max_per_other_vertical: int = DEFAULT_MAX_PER_OTHER_VERTICAL,
    language: str = "en",
) -> list[dict]:
    rows = _translation_candidates(db, entity_type, language)
    return _select_diverse(rows, target_vertical_id, limit, max_per_other_vertical, _translation_payload)


def _rejected_candidates(db: Session, entity_type: EntityType) -> list[_RejectedCandidate]:
    rows = db.query(
        KnowledgeRejectedEntity.vertical_id, KnowledgeVertical.name, KnowledgeRejectedEntity.name, KnowledgeRejectedEntity.reason, KnowledgeRejectedEntity.created_at
    ).join(KnowledgeVertical, KnowledgeVertical.id == KnowledgeRejectedEntity.vertical_id).filter(
        KnowledgeRejectedEntity.entity_type == entity_type
    ).order_by(KnowledgeRejectedEntity.created_at.desc()).limit(600).all()
    return [_RejectedCandidate(*row) for row in rows]


def _translation_candidates(db: Session, entity_type: EntityType, language: str) -> list[_TranslationCandidate]:
    rows = db.query(
        KnowledgeTranslationOverride.vertical_id, KnowledgeVertical.name, KnowledgeTranslationOverride.canonical_name, KnowledgeTranslationOverride.override_text, KnowledgeTranslationOverride.reason, KnowledgeTranslationOverride.created_at
    ).join(KnowledgeVertical, KnowledgeVertical.id == KnowledgeTranslationOverride.vertical_id).filter(
        KnowledgeTranslationOverride.entity_type == entity_type, KnowledgeTranslationOverride.language == language
    ).order_by(KnowledgeTranslationOverride.created_at.desc()).limit(600).all()
    return [_TranslationCandidate(*row) for row in rows]


def _select_diverse(
    rows: list,
    target_vertical_id: int | None,
    limit: int,
    max_per_other_vertical: int,
    payload_builder,
) -> list[dict]:
    same, other = _split_by_vertical(rows, target_vertical_id)
    picked = _pick_reason_first(same, limit)
    if len(picked) >= limit:
        return [_payload(target_vertical_id, c, payload_builder) for c in picked[:limit]]
    need = limit - len(picked)
    picked.extend(_diverse_other_verticals(other, need, max_per_other_vertical))
    return [_payload(target_vertical_id, c, payload_builder) for c in picked]


def _split_by_vertical(rows: list, target_vertical_id: int | None) -> tuple[list, list]:
    if not target_vertical_id:
        return [], list(rows)
    same = [r for r in rows if r.vertical_id == target_vertical_id]
    other = [r for r in rows if r.vertical_id != target_vertical_id]
    return same, other


def _pick_reason_first(rows: list, limit: int) -> list:
    reasonful = [r for r in rows if _has_reason(r)]
    boring = [r for r in rows if not _has_reason(r)]
    return (reasonful + boring)[:limit]


def _diverse_other_verticals(rows: list, need: int, max_per_vertical: int) -> list:
    reasonful = [r for r in rows if _has_reason(r)]
    boring = [r for r in rows if not _has_reason(r)]
    picked = _round_robin_with_fallback(reasonful, need, max_per_vertical)
    if len(picked) >= need:
        return picked
    picked.extend(_round_robin_with_fallback(boring, need - len(picked), max_per_vertical))
    return picked


def _round_robin(rows: list, need: int, max_per_vertical: int) -> list:
    groups = _group_by_vertical(rows)
    order = _vertical_order(groups)
    caps: dict[int, int] = defaultdict(int)
    picked: list = []
    while order and len(picked) < need:
        order = _round_robin_once(order, groups, caps, picked, max_per_vertical, need)
    return picked


def _round_robin_with_fallback(rows: list, need: int, max_per_vertical: int) -> list:
    picked = _round_robin(rows, need, max_per_vertical)
    if len(picked) >= need:
        return picked
    return _fill_remaining(rows, picked, need)


def _fill_remaining(rows: list, picked: list, need: int) -> list:
    picked_set = set(picked)
    for row in rows:
        if len(picked) >= need:
            return picked
        if row not in picked_set:
            picked.append(row)
    return picked


def _round_robin_once(
    vertical_ids: list[int],
    groups: dict[int, deque],
    caps: dict[int, int],
    picked: list,
    max_per_vertical: int,
    need: int,
) -> list[int]:
    remaining: list[int] = []
    for vertical_id in vertical_ids:
        if len(picked) >= need:
            return remaining
        queue = groups.get(vertical_id)
        if not queue or caps[vertical_id] >= max_per_vertical:
            continue
        picked.append(queue.popleft())
        caps[vertical_id] += 1
        if queue and caps[vertical_id] < max_per_vertical:
            remaining.append(vertical_id)
    return remaining


def _group_by_vertical(rows: list) -> dict[int, deque]:
    grouped: dict[int, deque] = {}
    buckets: dict[int, list] = defaultdict(list)
    for row in rows:
        buckets[row.vertical_id].append(row)
    for vertical_id, items in buckets.items():
        grouped[vertical_id] = deque(items)
    return grouped


def _vertical_order(groups: dict[int, deque]) -> list[int]:
    pairs = [(vertical_id, groups[vertical_id][0].created_at) for vertical_id in groups.keys() if groups[vertical_id]]
    pairs.sort(key=lambda p: p[1], reverse=True)
    return [vertical_id for vertical_id, _ in pairs]


def _has_reason(row) -> bool:
    reason = getattr(row, "reason", None)
    if reason is None:
        return False
    value = str(reason).strip()
    return value not in _BORING_REASONS


def _payload(target_vertical_id: int | None, row, payload_builder) -> dict:
    payload = payload_builder(row)
    payload["vertical_name"] = row.vertical_name
    payload["same_vertical"] = bool(target_vertical_id and row.vertical_id == target_vertical_id)
    return payload


def _rejected_payload(row: _RejectedCandidate) -> dict:
    return {"name": row.name, "reason": row.reason}


def _translation_payload(row: _TranslationCandidate) -> dict:
    return {"canonical_name": row.canonical_name, "override_text": row.override_text, "reason": row.reason}
