"""
Extraction augmentation with validated entities and previous mistakes.

This module provides functions to fetch validated brands/products and
previous rejection mistakes to augment the extraction prompt for
improved accuracy over time.
"""

import logging
from typing import Dict, List, Set, Tuple

from sqlalchemy.orm import Session

from models import EntityType, Vertical
from models.knowledge_domain import (
    KnowledgeAIAuditReviewItem,
    KnowledgeAIAuditReviewStatus,
    KnowledgeAIAuditRun,
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
)
from services.canonicalization_metrics import build_user_brand_variant_set, normalize_entity_key
from services.knowledge_examples import rejected_examples
from services.knowledge_session import knowledge_session
from services.knowledge_verticals import resolve_knowledge_vertical_id

logger = logging.getLogger(__name__)

POSITIVE_EXAMPLES_LIMIT = 20
NEGATIVE_EXAMPLES_LIMIT = 30
CORRECTION_EXAMPLES_LIMIT = 5

_CORRECTION_CONFIDENCE_LEVELS = {"VERY_HIGH", "HIGH"}


def get_validated_brands_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = POSITIVE_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get validated brands to include as positive examples in extraction prompt."""
    return _validated_brands_for_prompt(db, vertical_id, limit)


def get_validated_products_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = POSITIVE_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get validated products to include as positive examples in extraction prompt."""
    return _validated_products_for_prompt(db, vertical_id, limit)


def get_rejected_brands_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = NEGATIVE_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get rejected brands to include as negative examples in extraction prompt."""
    return _rejected_entities_for_prompt(db, vertical_id, EntityType.BRAND, limit)


def get_rejected_products_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = NEGATIVE_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get rejected products to include as negative examples in extraction prompt."""
    return _rejected_entities_for_prompt(db, vertical_id, EntityType.PRODUCT, limit)


def get_validated_entity_names(
    db: Session,
    vertical_id: int,
) -> Tuple[Set[str], Set[str]]:
    """Get sets of validated brand and product names for bypass checking.

    Returns:
        Tuple of (validated_brand_names, validated_product_names) as lowercase sets
    """
    return _validated_entity_names(db, vertical_id)


def get_augmentation_context(
    db: Session,
    vertical_id: int,
) -> Dict:
    """Get all augmentation data for extraction prompt.

    Returns dict with:
        - validated_brands: List of validated brand dicts
        - validated_products: List of validated product dicts
        - rejected_brands: List of rejected brand dicts
        - rejected_products: List of rejected product dicts
    """
    return _augmentation_context(db, vertical_id)

def get_correction_examples_for_prompt(
    db: Session,
    vertical_id: int,
    limit: int = CORRECTION_EXAMPLES_LIMIT,
) -> List[Dict]:
    """Get human/AI-approved correction examples to include in extraction prompt."""
    return _correction_examples_for_prompt(db, vertical_id, limit)


def _get_brand_aliases(db: Session, brand_id: int) -> List[str]:
    aliases = db.query(KnowledgeBrandAlias.alias).filter(
        KnowledgeBrandAlias.brand_id == brand_id
    ).all()
    return [alias for (alias,) in aliases]


def _get_product_aliases(db: Session, product_id: int) -> List[str]:
    aliases = db.query(KnowledgeProductAlias.alias).filter(
        KnowledgeProductAlias.product_id == product_id
    ).all()
    return [alias for (alias,) in aliases]


def _get_all_brand_aliases(db: Session, vertical_id: int) -> Set[str]:
    brand_ids = _validated_brand_ids(db, vertical_id)
    if not brand_ids:
        return set()
    aliases = db.query(KnowledgeBrandAlias.alias).filter(
        KnowledgeBrandAlias.brand_id.in_(brand_ids)
    ).all()
    return _alias_set(aliases)


def _get_all_product_aliases(db: Session, vertical_id: int) -> Set[str]:
    product_ids = _validated_product_ids(db, vertical_id)
    if not product_ids:
        return set()
    aliases = db.query(KnowledgeProductAlias.alias).filter(
        KnowledgeProductAlias.product_id.in_(product_ids)
    ).all()
    return _alias_set(aliases)


def _simplify_rejection_reason(reason: str) -> str:
    """Simplify rejection reason for display in prompt."""
    reason_map = {
        "light_filter": "generic term or too short",
        "rejected_at_light_filter": "generic term or too short",
        "rejected_at_normalization": "not a valid brand",
        "rejected_at_validation": "not a valid product",
        "rejected_at_list_filter": "not in primary position",
        "off_vertical": "off-vertical entity",
        "user_rejected": "manually rejected",
        "user_reject": "manually rejected",
    }
    return reason_map.get(reason, reason)


def get_canonical_for_validated_brand(
    db: Session,
    brand_name: str,
    vertical_id: int,
) -> str:
    """Get the canonical name for a validated brand."""
    return _canonical_for_validated_brand(db, brand_name, vertical_id)


def get_canonical_for_validated_product(
    db: Session,
    product_name: str,
    vertical_id: int,
) -> str:
    """Get the canonical name for a validated product."""
    return _canonical_for_validated_product(db, product_name, vertical_id)


def _validated_brands_for_prompt(db: Session, vertical_id: int, limit: int) -> List[Dict]:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        if not knowledge_id:
            return []
        return [_brand_prompt_entry(knowledge_db, b) for b in _validated_brands(knowledge_db, knowledge_id, limit)]


def _validated_products_for_prompt(db: Session, vertical_id: int, limit: int) -> List[Dict]:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        if not knowledge_id:
            return []
        return [_product_prompt_entry(knowledge_db, p) for p in _validated_products(knowledge_db, knowledge_id, limit)]


def _rejected_entities_for_prompt(
    db: Session,
    vertical_id: int,
    entity_type: EntityType,
    limit: int,
) -> List[Dict]:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        if not knowledge_id:
            return []
        examples = rejected_examples(knowledge_db, knowledge_id, entity_type, limit=limit)
        return [_rejected_prompt_item(example) for example in examples]


def _validated_entity_names(db: Session, vertical_id: int) -> Tuple[Set[str], Set[str]]:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        return _name_sets(db, knowledge_db, knowledge_id, vertical_id)


def _augmentation_context(db: Session, vertical_id: int) -> Dict:
    return {
        "validated_brands": get_validated_brands_for_prompt(db, vertical_id),
        "validated_products": get_validated_products_for_prompt(db, vertical_id),
        "rejected_brands": get_rejected_brands_for_prompt(db, vertical_id),
        "rejected_products": get_rejected_products_for_prompt(db, vertical_id),
        "correction_examples": get_correction_examples_for_prompt(db, vertical_id),
    }


def _knowledge_vertical_id(knowledge_db: Session, db: Session, vertical_id: int) -> int | None:
    name = _vertical_name(db, vertical_id)
    if not name:
        return None
    return resolve_knowledge_vertical_id(knowledge_db, name)


def _vertical_name(db: Session, vertical_id: int) -> str:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    return vertical.name if vertical else ""


def _validated_brands(knowledge_db: Session, vertical_id: int, limit: int) -> List[KnowledgeBrand]:
    return knowledge_db.query(KnowledgeBrand).filter(
        KnowledgeBrand.vertical_id == vertical_id,
        KnowledgeBrand.is_validated == True,
    ).order_by(KnowledgeBrand.updated_at.desc()).limit(limit).all()


def _validated_products(knowledge_db: Session, vertical_id: int, limit: int) -> List[KnowledgeProduct]:
    return knowledge_db.query(KnowledgeProduct).filter(
        KnowledgeProduct.vertical_id == vertical_id,
        KnowledgeProduct.is_validated == True,
    ).order_by(KnowledgeProduct.updated_at.desc()).limit(limit).all()

def _correction_examples_for_prompt(db: Session, vertical_id: int, limit: int) -> List[Dict]:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        rows = _applied_correction_rows(knowledge_db, knowledge_id)
        return _select_correction_examples(rows, limit)


def _applied_correction_rows(knowledge_db: Session, knowledge_vertical_id: int | None) -> list[KnowledgeAIAuditReviewItem]:
    if not knowledge_vertical_id:
        return []
    return knowledge_db.query(KnowledgeAIAuditReviewItem).join(
        KnowledgeAIAuditRun, KnowledgeAIAuditRun.id == KnowledgeAIAuditReviewItem.audit_run_id
    ).filter(
        KnowledgeAIAuditRun.vertical_id == knowledge_vertical_id,
        KnowledgeAIAuditReviewItem.status == KnowledgeAIAuditReviewStatus.APPLIED,
        KnowledgeAIAuditReviewItem.confidence_level.in_(_CORRECTION_CONFIDENCE_LEVELS),
        KnowledgeAIAuditReviewItem.evidence_quote_zh.isnot(None),
        KnowledgeAIAuditReviewItem.evidence_quote_zh != "",
    ).order_by(KnowledgeAIAuditReviewItem.applied_at.desc()).limit(300).all()


def _select_correction_examples(rows: list[KnowledgeAIAuditReviewItem], limit: int) -> List[Dict]:
    candidates = [_candidate_or_none(r) for r in rows]
    ordered = _order_candidates([c for c in candidates if c])
    chosen = _choose_diverse(ordered, limit)
    return [{"trigger": c["trigger"], "rules": c["rules"]} for c in chosen]


def _order_candidates(candidates: list[dict]) -> list[dict]:
    return sorted(candidates, key=_candidate_rank)


def _candidate_rank(candidate: dict) -> tuple:
    level = str(candidate.get("confidence_level") or "")
    return (_level_priority(level), -float(candidate.get("confidence_score") or 0.0), -int(candidate.get("applied_at") or 0))


def _level_priority(level: str) -> int:
    return 0 if level == "VERY_HIGH" else 1


def _choose_diverse(candidates: list[dict], limit: int) -> list[dict]:
    if limit <= 0:
        return []
    picked, seen = [], set()
    picked, seen = _pick_mapping_first(candidates, picked, seen, limit)
    picked, seen = _pick_kind(candidates, picked, seen, limit, "brand")
    picked, seen = _pick_kind(candidates, picked, seen, limit, "product")
    return _fill_remaining(candidates, picked, seen, limit)


def _pick_mapping_first(candidates: list[dict], picked: list[dict], seen: set, limit: int) -> tuple[list[dict], set]:
    for c in candidates:
        if len(picked) >= limit:
            return picked, seen
        if c.get("kind") == "mapping" and c["dedupe_key"] not in seen:
            picked.append(c)
            seen.add(c["dedupe_key"])
            return picked, seen
    return picked, seen


def _pick_kind(candidates: list[dict], picked: list[dict], seen: set, limit: int, kind: str) -> tuple[list[dict], set]:
    for c in candidates:
        if len(picked) >= limit:
            return picked, seen
        if c.get("kind") == kind and c["dedupe_key"] not in seen:
            picked.append(c)
            seen.add(c["dedupe_key"])
            return picked, seen
    return picked, seen


def _fill_remaining(candidates: list[dict], picked: list[dict], seen: set, limit: int) -> list[dict]:
    for c in candidates:
        if len(picked) >= limit:
            return picked
        if c["dedupe_key"] in seen:
            continue
        picked.append(c)
        seen.add(c["dedupe_key"])
    return picked


def _candidate_or_none(row: KnowledgeAIAuditReviewItem) -> dict | None:
    payload = row.feedback_payload or {}
    trigger = (row.evidence_quote_zh or "").strip()
    example = _payload_example(payload, trigger)
    if not example:
        return None
    if not _trigger_ok(trigger, example):
        return None
    return {**example, "confidence_level": row.confidence_level, "confidence_score": row.confidence_score, "applied_at": _ts(row.applied_at)}


def _ts(value) -> int:
    return int(value.timestamp()) if value else 0


def _payload_example(payload: dict, trigger: str) -> dict | None:
    if item := _mapping_item(payload):
        return _mapping_example(item, trigger)
    if item := _brand_item(payload):
        return _brand_example(item, trigger)
    if item := _product_item(payload):
        return _product_example(item, trigger)
    return None


def _mapping_item(payload: dict) -> dict | None:
    items = payload.get("mapping_feedback") or []
    return items[0] if items else None


def _brand_item(payload: dict) -> dict | None:
    items = payload.get("brand_feedback") or []
    return items[0] if items else None


def _product_item(payload: dict) -> dict | None:
    items = payload.get("product_feedback") or []
    return items[0] if items else None


def _mapping_example(item: dict, trigger: str) -> dict | None:
    product = (item.get("product_name") or "").strip()
    brand = (item.get("brand_name") or "").strip()
    action = (item.get("action") or "").strip()
    if not product or not brand:
        return None
    rules = _mapping_rules(product, brand, action)
    return {"kind": "mapping", "trigger": trigger, "rules": rules, "dedupe_key": _mapping_key(product, brand, action)}


def _mapping_rules(product: str, brand: str, action: str) -> list[str]:
    if action == "reject":
        return [f'If you extract product "{product}", MUST NOT set parent_brand to "{brand}".']
    return [f'If you extract product "{product}" and brand "{brand}", output {{"name":"{product}","type":"product","parent_brand":"{brand}"}}.']


def _mapping_key(product: str, brand: str, action: str) -> str:
    return f"mapping:{action}:{normalize_entity_key(product)}:{normalize_entity_key(brand)}"


def _brand_example(item: dict, trigger: str) -> dict | None:
    return _entity_example(item, trigger, "brand")


def _product_example(item: dict, trigger: str) -> dict | None:
    return _entity_example(item, trigger, "product")


def _entity_example(item: dict, trigger: str, label: str) -> dict | None:
    action = (item.get("action") or "").strip()
    wrong = (item.get("wrong_name") or "").strip()
    correct = (item.get("correct_name") or "").strip()
    name = (item.get("name") or "").strip()
    if action == "replace" and wrong and correct:
        rules = [f'MUST NOT extract {label} "{wrong}".', f'If the text contains "{correct}" as a standalone entity, extract {label} "{correct}".']
        return {"kind": label, "trigger": trigger, "rules": rules, "dedupe_key": _replace_key(label, wrong, correct)}
    if action == "reject" and name:
        return {"kind": label, "trigger": trigger, "rules": [f'MUST NOT extract {label} "{name}".'], "dedupe_key": _simple_key(label, "reject", name)}
    if action == "validate" and name:
        rule = f'If the text contains "{name}" as a standalone entity, extract {label} "{name}".'
        return {"kind": label, "trigger": trigger, "rules": [rule], "dedupe_key": _simple_key(label, "validate", name)}
    return None


def _replace_key(label: str, wrong: str, correct: str) -> str:
    return f"{label}:replace:{normalize_entity_key(wrong)}:{normalize_entity_key(correct)}"


def _simple_key(label: str, action: str, name: str) -> str:
    return f"{label}:{action}:{normalize_entity_key(name)}"


def _trigger_ok(trigger: str, example: dict) -> bool:
    if example.get("kind") == "mapping":
        return _mapping_trigger_ok(trigger, example.get("rules") or [])
    return _entity_trigger_ok(trigger, example.get("rules") or [])


def _mapping_trigger_ok(trigger: str, rules: list[str]) -> bool:
    text = trigger.casefold()
    parts = [p for p in _quoted_parts(rules) if p]
    return all(p.casefold() in text for p in parts[:2])


def _entity_trigger_ok(trigger: str, rules: list[str]) -> bool:
    text = trigger.casefold()
    parts = [p for p in _quoted_parts(rules) if p]
    return bool(parts) and parts[0].casefold() in text


def _quoted_parts(rules: list[str]) -> list[str]:
    return [part for r in rules for part in _extract_quoted(r)]


def _extract_quoted(text: str) -> list[str]:
    import re

    return re.findall(r'"([^"]+)"', text or "")


def _brand_prompt_entry(knowledge_db: Session, brand: KnowledgeBrand) -> Dict:
    return {
        "canonical_name": brand.canonical_name,
        "display_name": brand.display_name,
        "aliases": _get_brand_aliases(knowledge_db, brand.id),
    }


def _product_prompt_entry(knowledge_db: Session, product: KnowledgeProduct) -> Dict:
    return {
        "canonical_name": product.canonical_name,
        "display_name": product.display_name,
        "aliases": _get_product_aliases(knowledge_db, product.id),
    }


def _rejected_prompt_item(example: dict) -> Dict:
    reason = _simplify_rejection_reason(example.get("reason") or "")
    return {
        "name": example.get("name") or "",
        "reason": reason,
        "vertical_name": example.get("vertical_name") or "",
        "same_vertical": bool(example.get("same_vertical")),
    }


def _name_sets(
    db: Session,
    knowledge_db: Session,
    knowledge_vertical_id: int | None,
    vertical_id: int,
) -> Tuple[Set[str], Set[str]]:
    if not knowledge_vertical_id:
        return build_user_brand_variant_set(db, vertical_id), set()
    brand_names = _validated_name_set(knowledge_db, knowledge_vertical_id, KnowledgeBrand)
    product_names = _validated_name_set(knowledge_db, knowledge_vertical_id, KnowledgeProduct)
    brand_names.update(_get_all_brand_aliases(knowledge_db, knowledge_vertical_id))
    product_names.update(_get_all_product_aliases(knowledge_db, knowledge_vertical_id))
    brand_names.update(build_user_brand_variant_set(db, vertical_id))
    return brand_names, product_names


def _validated_name_set(knowledge_db: Session, vertical_id: int, model) -> Set[str]:
    rows = knowledge_db.query(model.canonical_name).filter(
        model.vertical_id == vertical_id,
        model.is_validated == True,
    ).all()
    return _name_set(rows)


def _name_set(rows: List[Tuple[str]]) -> Set[str]:
    result: Set[str] = set()
    for (name,) in rows:
        result.add(name.lower())
        result.add(name)
    return result


def _validated_brand_ids(db: Session, vertical_id: int) -> List[int]:
    return _validated_ids(db, vertical_id, KnowledgeBrand)


def _validated_product_ids(db: Session, vertical_id: int) -> List[int]:
    return _validated_ids(db, vertical_id, KnowledgeProduct)


def _validated_ids(db: Session, vertical_id: int, model) -> List[int]:
    rows = db.query(model.id).filter(
        model.vertical_id == vertical_id,
        model.is_validated == True,
    ).all()
    return [row[0] for row in rows]


def _alias_set(rows: List[Tuple[str]]) -> Set[str]:
    result: Set[str] = set()
    for (alias,) in rows:
        result.add(alias.lower())
        result.add(alias)
    return result


def _canonical_for_validated_brand(db: Session, brand_name: str, vertical_id: int) -> str:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        return _canonical_name_for_entity(
            knowledge_db, knowledge_id, KnowledgeBrand, KnowledgeBrandAlias, brand_name
        )


def _canonical_for_validated_product(db: Session, product_name: str, vertical_id: int) -> str:
    with knowledge_session() as knowledge_db:
        knowledge_id = _knowledge_vertical_id(knowledge_db, db, vertical_id)
        return _canonical_name_for_entity(
            knowledge_db, knowledge_id, KnowledgeProduct, KnowledgeProductAlias, product_name
        )


def _canonical_name_for_entity(
    knowledge_db: Session,
    knowledge_vertical_id: int | None,
    model,
    alias_model,
    name: str,
) -> str:
    if not knowledge_vertical_id:
        return name
    canonical = _find_canonical(knowledge_db, knowledge_vertical_id, model, name)
    if canonical:
        return canonical.canonical_name
    alias = _find_alias_canonical(knowledge_db, knowledge_vertical_id, model, alias_model, name)
    return alias.canonical_name if alias else name


def _find_canonical(knowledge_db: Session, vertical_id: int, model, name: str):
    from sqlalchemy import func

    return knowledge_db.query(model).filter(
        model.vertical_id == vertical_id,
        model.is_validated == True,
        func.lower(model.canonical_name) == name.casefold(),
    ).first()


def _find_alias_canonical(
    knowledge_db: Session,
    vertical_id: int,
    model,
    alias_model,
    name: str,
):
    from sqlalchemy import func

    return knowledge_db.query(model).join(alias_model).filter(
        model.vertical_id == vertical_id,
        model.is_validated == True,
        func.lower(alias_model.alias) == name.casefold(),
    ).first()
