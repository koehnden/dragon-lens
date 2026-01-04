import logging
import os
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from models import (
    Brand,
    BrandAlias,
    BrandMention,
    CanonicalBrand,
    CanonicalProduct,
    EntityType,
    LLMAnswer,
    Product,
    ProductAlias,
    ProductMention,
    RejectedEntity,
    Run,
    ValidationCandidate,
    ValidationStatus,
    Vertical,
)
from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
    KnowledgeRejectedEntity,
)
from services.canonicalization_metrics import normalize_entity_key
from services.knowledge_session import knowledge_session
from services.knowledge_verticals import (
    ensure_vertical_alias,
    get_or_create_vertical,
    resolve_knowledge_vertical_id,
)

logger = logging.getLogger(__name__)

MIN_MENTION_COUNT_FOR_AUTO_VALIDATE = int(os.getenv("MIN_MENTION_COUNT_AUTO_VALIDATE", "3"))
SIMILARITY_THRESHOLD = float(os.getenv("ENTITY_SIMILARITY_THRESHOLD", "0.85"))


@dataclass
class MergeCandidate:
    source_name: str
    target_name: str
    similarity: float
    entity_type: EntityType


@dataclass
class ConsolidationResult:
    brands_merged: int
    products_merged: int
    brands_flagged: int
    products_flagged: int
    canonical_brands_created: int
    canonical_products_created: int


def consolidate_run(
    db: Session,
    run_id: int,
    normalized_brands: Optional[Dict[str, str]] = None,
) -> ConsolidationResult:
    logger.info(f"Starting entity consolidation for run {run_id}")

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    vertical_id = run.vertical_id
    _ensure_knowledge_vertical_id(db, vertical_id)
    ensure_user_brand_canonicals(db, vertical_id)

    brand_mentions = _collect_brand_mentions(db, run_id)
    product_mentions = _collect_product_mentions(db, run_id)

    qwen_candidates, grouped_names = _build_qwen_brand_candidates(
        db, vertical_id, normalized_brands
    )
    brand_merge_candidates = find_merge_candidates(
        list(brand_mentions.keys()), EntityType.BRAND
    )
    brand_merge_candidates = [
        c for c in brand_merge_candidates if c.source_name not in grouped_names
    ]
    brand_merge_candidates.extend(qwen_candidates)
    product_merge_candidates = find_merge_candidates(
        list(product_mentions.keys()), EntityType.PRODUCT
    )

    brands_merged = apply_brand_merges(
        db, vertical_id, brand_mentions, brand_merge_candidates
    )
    products_merged = apply_product_merges(
        db, vertical_id, product_mentions, product_merge_candidates
    )

    brands_flagged = flag_low_frequency_brands(db, vertical_id, brand_mentions)
    products_flagged = flag_low_frequency_products(db, vertical_id, product_mentions)

    canonical_brands, canonical_products = _knowledge_canonical_counts(db, vertical_id)

    db.commit()

    logger.info(
        f"Consolidation complete: {brands_merged} brands merged, "
        f"{products_merged} products merged, {brands_flagged} brands flagged, "
        f"{products_flagged} products flagged"
    )

    return ConsolidationResult(
        brands_merged=brands_merged,
        products_merged=products_merged,
        brands_flagged=brands_flagged,
        products_flagged=products_flagged,
        canonical_brands_created=canonical_brands,
        canonical_products_created=canonical_products,
    )


def _collect_brand_mentions(db: Session, run_id: int) -> Dict[str, int]:
    answers = db.query(LLMAnswer).filter(LLMAnswer.run_id == run_id).all()
    mentions: Dict[str, int] = {}

    for answer in answers:
        brand_mentions = db.query(BrandMention).filter(
            BrandMention.llm_answer_id == answer.id,
            BrandMention.mentioned == True,
        ).all()

        for mention in brand_mentions:
            brand = db.query(Brand).filter(Brand.id == mention.brand_id).first()
            if brand:
                name = brand.display_name
                mentions[name] = mentions.get(name, 0) + 1

    return mentions


def _collect_product_mentions(db: Session, run_id: int) -> Dict[str, int]:
    answers = db.query(LLMAnswer).filter(LLMAnswer.run_id == run_id).all()
    mentions: Dict[str, int] = {}

    for answer in answers:
        product_mentions = db.query(ProductMention).filter(
            ProductMention.llm_answer_id == answer.id,
            ProductMention.mentioned == True,
        ).all()

        for mention in product_mentions:
            product = db.query(Product).filter(Product.id == mention.product_id).first()
            if product:
                name = product.display_name
                mentions[name] = mentions.get(name, 0) + 1

    return mentions


def find_merge_candidates(
    entity_names: List[str], entity_type: EntityType
) -> List[MergeCandidate]:
    candidates: List[MergeCandidate] = []
    processed: Set[Tuple[str, str]] = set()

    normalized_map = {name: _normalize_for_comparison(name) for name in entity_names}

    for i, name1 in enumerate(entity_names):
        for name2 in entity_names[i + 1:]:
            pair_key = tuple(sorted([name1, name2]))
            if pair_key in processed:
                continue
            processed.add(pair_key)

            similarity = _calculate_similarity(
                normalized_map[name1], normalized_map[name2]
            )

            if similarity >= SIMILARITY_THRESHOLD:
                target, source = _determine_canonical(name1, name2)
                candidates.append(MergeCandidate(
                    source_name=source,
                    target_name=target,
                    similarity=similarity,
                    entity_type=entity_type,
                ))

    return candidates


def _normalize_for_comparison(name: str) -> str:
    return normalize_entity_key(name)


def _calculate_similarity(name1: str, name2: str) -> float:
    if name1 == name2:
        return 1.0

    if name1 in name2 or name2 in name1:
        shorter = min(len(name1), len(name2))
        longer = max(len(name1), len(name2))
        return shorter / longer if longer > 0 else 0.0

    return SequenceMatcher(None, name1, name2).ratio()


def _determine_canonical(name1: str, name2: str) -> Tuple[str, str]:
    score1 = _canonical_score(name1)
    score2 = _canonical_score(name2)
    if score1 < score2:
        return name1, name2
    if score2 < score1:
        return name2, name1
    return (name1, name2) if name1 < name2 else (name2, name1)


def _canonical_score(name: str) -> Tuple[int, int, str]:
    normalized = _normalize_for_comparison(name)
    return (len(normalized), len(name), name.casefold())


def _build_qwen_brand_candidates(
    db: Session,
    vertical_id: int,
    normalized_brands: Optional[Dict[str, str]],
) -> Tuple[List[MergeCandidate], Set[str]]:
    if not normalized_brands:
        return [], set()
    brands = _load_brands(db, vertical_id)
    exact, norm = _qwen_maps(normalized_brands)
    groups = _group_brands_by_qwen(brands, exact, norm)
    validated = _validated_canonical_names(db, vertical_id)
    return _qwen_merge_candidates(groups, validated), _grouped_display_names(groups)


def _load_brands(db: Session, vertical_id: int) -> List[Brand]:
    return db.query(Brand).filter(Brand.vertical_id == vertical_id).all()


def _qwen_maps(normalized_brands: Dict[str, str]) -> Tuple[Dict[str, str], Dict[str, str]]:
    exact = {k.casefold(): v for k, v in normalized_brands.items() if k}
    norm = { _normalize_for_comparison(k): v for k, v in normalized_brands.items() if k}
    return exact, norm


def _brand_variants_for_qwen(brand: Brand) -> List[str]:
    values = [brand.display_name, brand.original_name, brand.translated_name or ""]
    return [v for v in values if v]


def _resolve_qwen_canonical(
    brand: Brand,
    exact: Dict[str, str],
    norm: Dict[str, str],
) -> Optional[str]:
    for name in _brand_variants_for_qwen(brand):
        if key := exact.get(name.casefold()):
            return key
        if key := norm.get(_normalize_for_comparison(name)):
            return key
    return None


def _group_brands_by_qwen(
    brands: List[Brand],
    exact: Dict[str, str],
    norm: Dict[str, str],
) -> Dict[str, List[Brand]]:
    grouped: Dict[str, List[Brand]] = {}
    for brand in brands:
        key = _resolve_qwen_canonical(brand, exact, norm)
        if key:
            grouped.setdefault(key, []).append(brand)
    return grouped


def _validated_canonical_names(db: Session, vertical_id: int) -> Set[str]:
    knowledge_id = _knowledge_vertical_id(db, vertical_id)
    if knowledge_id:
        return _knowledge_validated_brand_names(knowledge_id)
    return _legacy_validated_brand_names(db, vertical_id)


def _group_name_keys(brands: List[Brand]) -> Set[str]:
    keys: Set[str] = set()
    for brand in brands:
        for name in _brand_variants_for_qwen(brand):
            keys.add(_normalize_for_comparison(name))
    return keys


def _qwen_canonical_allowed(
    canonical: Optional[str],
    brands: List[Brand],
    validated: Set[str],
) -> bool:
    if not canonical:
        return False
    if canonical.casefold() in validated:
        return True
    return _normalize_for_comparison(canonical) in _group_name_keys(brands)


def _cleanest_name_from_group(brands: List[Brand]) -> str:
    names = [b.display_name for b in brands if b.display_name]
    return sorted(names, key=_canonical_score)[0]


def _choose_group_canonical(
    brands: List[Brand],
    qwen_key: str,
    validated: Set[str],
) -> str:
    users = [b for b in brands if b.is_user_input]
    if users:
        return _cleanest_name_from_group(users)
    if _qwen_canonical_allowed(qwen_key, brands, validated):
        return qwen_key
    return _cleanest_name_from_group(brands)


def _brand_candidate(source_name: str, target_name: str) -> MergeCandidate:
    return MergeCandidate(
        source_name=source_name,
        target_name=target_name,
        similarity=1.0,
        entity_type=EntityType.BRAND,
    )


def _qwen_group_candidates(
    qwen_key: str,
    brands: List[Brand],
    validated: Set[str],
) -> List[MergeCandidate]:
    target = _choose_group_canonical(brands, qwen_key, validated)
    return [
        _brand_candidate(brand.display_name, target)
        for brand in brands
        if brand.display_name != target
    ]


def _qwen_merge_candidates(
    groups: Dict[str, List[Brand]],
    validated: Set[str],
) -> List[MergeCandidate]:
    candidates: List[MergeCandidate] = []
    for key, brands in groups.items():
        candidates.extend(_qwen_group_candidates(key, brands, validated))
    return candidates


def _grouped_display_names(groups: Dict[str, List[Brand]]) -> Set[str]:
    return {brand.display_name for group in groups.values() for brand in group}


def _user_brand_aliases(brand: Brand) -> List[str]:
    aliases = brand.aliases or {}
    values = (aliases.get("zh") or []) + (aliases.get("en") or [])
    candidates = [brand.original_name, brand.translated_name or ""] + values
    return [v for v in candidates if v and v != brand.display_name]


def ensure_user_brand_canonicals(db: Session, vertical_id: int) -> None:
    brands = db.query(Brand).filter(Brand.vertical_id == vertical_id, Brand.is_user_input == True).all()
    for brand in brands:
        canonical = _get_or_create_canonical_brand(db, vertical_id, brand.display_name, 0)
        canonical.display_name = brand.display_name
        canonical.is_validated = True
        canonical.validation_source = "user"
        _mark_knowledge_brand_validated(db, vertical_id, brand.display_name, "user")
        for alias in _user_brand_aliases(brand):
            _add_brand_alias(db, vertical_id, canonical.id, alias)


def apply_brand_merges(
    db: Session,
    vertical_id: int,
    mentions: Dict[str, int],
    candidates: List[MergeCandidate],
) -> int:
    merged_count = 0
    merge_map: Dict[str, str] = {}

    for candidate in candidates:
        if candidate.entity_type != EntityType.BRAND:
            continue
        merge_map[candidate.source_name] = candidate.target_name
        logger.info(
            f"Merging brand '{candidate.source_name}' -> '{candidate.target_name}' "
            f"(similarity: {candidate.similarity:.2f})"
        )

    processed_targets: Set[str] = set()

    for source_name, target_name in merge_map.items():
        final_target = _resolve_merge_chain(target_name, merge_map)

        if final_target not in processed_targets:
            total_mentions = mentions.get(final_target, 0)
            for src, tgt in merge_map.items():
                if _resolve_merge_chain(tgt, merge_map) == final_target:
                    total_mentions += mentions.get(src, 0)

            canonical = _get_or_create_canonical_brand(
                db, vertical_id, final_target, total_mentions
            )
            processed_targets.add(final_target)

        canonical = db.query(CanonicalBrand).filter(
            CanonicalBrand.vertical_id == vertical_id,
            CanonicalBrand.canonical_name == final_target,
        ).first()

        if canonical:
            _add_brand_alias(db, vertical_id, canonical.id, source_name)
            merged_count += 1

    for name, count in mentions.items():
        if name in merge_map:
            continue
        if name in processed_targets:
            continue

        _get_or_create_canonical_brand(db, vertical_id, name, count)

    return merged_count


def apply_product_merges(
    db: Session,
    vertical_id: int,
    mentions: Dict[str, int],
    candidates: List[MergeCandidate],
) -> int:
    merged_count = 0
    merge_map: Dict[str, str] = {}

    for candidate in candidates:
        if candidate.entity_type != EntityType.PRODUCT:
            continue
        merge_map[candidate.source_name] = candidate.target_name
        logger.info(
            f"Merging product '{candidate.source_name}' -> '{candidate.target_name}' "
            f"(similarity: {candidate.similarity:.2f})"
        )

    processed_targets: Set[str] = set()

    for source_name, target_name in merge_map.items():
        final_target = _resolve_merge_chain(target_name, merge_map)

        if final_target not in processed_targets:
            total_mentions = mentions.get(final_target, 0)
            for src, tgt in merge_map.items():
                if _resolve_merge_chain(tgt, merge_map) == final_target:
                    total_mentions += mentions.get(src, 0)

            canonical = _get_or_create_canonical_product(
                db, vertical_id, final_target, total_mentions
            )
            processed_targets.add(final_target)

        canonical = db.query(CanonicalProduct).filter(
            CanonicalProduct.vertical_id == vertical_id,
            CanonicalProduct.canonical_name == final_target,
        ).first()

        if canonical:
            _add_product_alias(db, vertical_id, canonical.id, source_name)
            merged_count += 1

    for name, count in mentions.items():
        if name in merge_map:
            continue
        if name in processed_targets:
            continue

        _get_or_create_canonical_product(db, vertical_id, name, count)

    return merged_count


def _resolve_merge_chain(name: str, merge_map: Dict[str, str]) -> str:
    visited: Set[str] = set()
    current = name

    while current in merge_map and current not in visited:
        visited.add(current)
        current = merge_map[current]

    return current


def _get_or_create_canonical_brand(
    db: Session, vertical_id: int, name: str, mention_count: int
) -> CanonicalBrand:
    _upsert_knowledge_brand(db, vertical_id, name, mention_count, None)
    existing = db.query(CanonicalBrand).filter(
        CanonicalBrand.vertical_id == vertical_id,
        CanonicalBrand.canonical_name == name,
    ).first()

    if existing:
        existing.mention_count += mention_count
        return existing

    is_validated = mention_count >= MIN_MENTION_COUNT_FOR_AUTO_VALIDATE

    canonical = CanonicalBrand(
        vertical_id=vertical_id,
        canonical_name=name,
        display_name=name,
        is_validated=is_validated,
        validation_source="auto" if is_validated else None,
        mention_count=mention_count,
    )
    db.add(canonical)
    db.flush()

    return canonical


def _get_or_create_canonical_product(
    db: Session, vertical_id: int, name: str, mention_count: int
) -> CanonicalProduct:
    _upsert_knowledge_product(db, vertical_id, None, name, mention_count, None)
    existing = db.query(CanonicalProduct).filter(
        CanonicalProduct.vertical_id == vertical_id,
        CanonicalProduct.canonical_name == name,
    ).first()

    if existing:
        existing.mention_count += mention_count
        return existing

    is_validated = mention_count >= MIN_MENTION_COUNT_FOR_AUTO_VALIDATE

    canonical = CanonicalProduct(
        vertical_id=vertical_id,
        canonical_name=name,
        display_name=name,
        is_validated=is_validated,
        validation_source="auto" if is_validated else None,
        mention_count=mention_count,
    )
    db.add(canonical)
    db.flush()

    return canonical


def _add_brand_alias(db: Session, vertical_id: int, canonical_id: int, alias_name: str) -> None:
    existing = db.query(BrandAlias).filter(
        BrandAlias.canonical_brand_id == canonical_id,
        BrandAlias.alias == alias_name,
    ).first()

    if not existing:
        alias = BrandAlias(canonical_brand_id=canonical_id, alias=alias_name)
        db.add(alias)
    _add_knowledge_brand_alias(db, vertical_id, canonical_id, alias_name)


def _add_product_alias(db: Session, vertical_id: int, canonical_id: int, alias_name: str) -> None:
    existing = db.query(ProductAlias).filter(
        ProductAlias.canonical_product_id == canonical_id,
        ProductAlias.alias == alias_name,
    ).first()

    if not existing:
        alias = ProductAlias(canonical_product_id=canonical_id, alias=alias_name)
        db.add(alias)
    _add_knowledge_product_alias(db, vertical_id, canonical_id, alias_name)


def flag_low_frequency_brands(
    db: Session, vertical_id: int, mentions: Dict[str, int]
) -> int:
    flagged_count = 0

    for name, count in mentions.items():
        if count >= MIN_MENTION_COUNT_FOR_AUTO_VALIDATE:
            continue

        existing = db.query(ValidationCandidate).filter(
            ValidationCandidate.vertical_id == vertical_id,
            ValidationCandidate.entity_type == EntityType.BRAND,
            ValidationCandidate.name == name,
        ).first()

        if existing:
            existing.mention_count += count
            continue

        candidate = ValidationCandidate(
            vertical_id=vertical_id,
            entity_type=EntityType.BRAND,
            name=name,
            mention_count=count,
            status=ValidationStatus.PENDING,
        )
        db.add(candidate)
        flagged_count += 1

    return flagged_count


def flag_low_frequency_products(
    db: Session, vertical_id: int, mentions: Dict[str, int]
) -> int:
    flagged_count = 0

    for name, count in mentions.items():
        if count >= MIN_MENTION_COUNT_FOR_AUTO_VALIDATE:
            continue

        existing = db.query(ValidationCandidate).filter(
            ValidationCandidate.vertical_id == vertical_id,
            ValidationCandidate.entity_type == EntityType.PRODUCT,
            ValidationCandidate.name == name,
        ).first()

        if existing:
            existing.mention_count += count
            continue

        candidate = ValidationCandidate(
            vertical_id=vertical_id,
            entity_type=EntityType.PRODUCT,
            name=name,
            mention_count=count,
            status=ValidationStatus.PENDING,
        )
        db.add(candidate)
        flagged_count += 1

    return flagged_count


def validate_candidate(
    db: Session, candidate_id: int, approved: bool, rejection_reason: Optional[str] = None
) -> ValidationCandidate:
    candidate = db.query(ValidationCandidate).filter(
        ValidationCandidate.id == candidate_id
    ).first()

    if not candidate:
        raise ValueError(f"Validation candidate {candidate_id} not found")

    from datetime import datetime

    if approved:
        candidate.status = ValidationStatus.VALIDATED
        candidate.reviewed_at = datetime.utcnow()
        candidate.reviewed_by = "user"

        if candidate.entity_type == EntityType.BRAND:
            _get_or_create_canonical_brand(
                db, candidate.vertical_id, candidate.name, candidate.mention_count
            )
            _mark_knowledge_brand_validated(db, candidate.vertical_id, candidate.name, "user")
        else:
            _get_or_create_canonical_product(
                db, candidate.vertical_id, candidate.name, candidate.mention_count
            )
            _mark_knowledge_product_validated(db, candidate.vertical_id, candidate.name, "user")
    else:
        candidate.status = ValidationStatus.REJECTED
        candidate.reviewed_at = datetime.utcnow()
        candidate.reviewed_by = "user"
        candidate.rejection_reason = rejection_reason

        rejected = RejectedEntity(
            vertical_id=candidate.vertical_id,
            entity_type=candidate.entity_type,
            name=candidate.name,
            rejection_reason=rejection_reason or "User rejected",
        )
        db.add(rejected)
        _add_knowledge_rejection(
            db, candidate.vertical_id, candidate.entity_type, candidate.name, rejection_reason
        )

    db.commit()
    return candidate


def get_pending_candidates(
    db: Session, vertical_id: int, entity_type: Optional[EntityType] = None
) -> List[ValidationCandidate]:
    query = db.query(ValidationCandidate).filter(
        ValidationCandidate.vertical_id == vertical_id,
        ValidationCandidate.status == ValidationStatus.PENDING,
    )

    if entity_type:
        query = query.filter(ValidationCandidate.entity_type == entity_type)

    return query.order_by(ValidationCandidate.mention_count.desc()).all()


def get_canonical_brands(db: Session, vertical_id: int) -> List[object]:
    return _knowledge_brands_or_legacy(db, vertical_id)


def get_canonical_products(db: Session, vertical_id: int) -> List[object]:
    return _knowledge_products_or_legacy(db, vertical_id)


def _knowledge_vertical_id(db: Session, vertical_id: int) -> int | None:
    name = _vertical_name(db, vertical_id)
    if not name:
        return None
    with knowledge_session() as knowledge_db:
        return resolve_knowledge_vertical_id(knowledge_db, name)


def _ensure_knowledge_vertical_id(db: Session, vertical_id: int) -> int | None:
    name = _vertical_name(db, vertical_id)
    if not name:
        return None
    with knowledge_session() as knowledge_db:
        vertical = get_or_create_vertical(knowledge_db, name)
        ensure_vertical_alias(knowledge_db, vertical.id, name)
        knowledge_db.commit()
        return vertical.id


def _vertical_name(db: Session, vertical_id: int) -> str:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    return vertical.name if vertical else ""


def _knowledge_canonical_counts(db: Session, vertical_id: int) -> Tuple[int, int]:
    knowledge_id = _knowledge_vertical_id(db, vertical_id)
    if not knowledge_id:
        return _legacy_canonical_counts(db, vertical_id)
    with knowledge_session() as knowledge_db:
        return _knowledge_counts(knowledge_db, knowledge_id)


def _legacy_canonical_counts(db: Session, vertical_id: int) -> Tuple[int, int]:
    return (
        db.query(CanonicalBrand).filter(CanonicalBrand.vertical_id == vertical_id).count(),
        db.query(CanonicalProduct).filter(CanonicalProduct.vertical_id == vertical_id).count(),
    )


def _knowledge_counts(knowledge_db: Session, vertical_id: int) -> Tuple[int, int]:
    return (
        knowledge_db.query(KnowledgeBrand).filter(KnowledgeBrand.vertical_id == vertical_id).count(),
        knowledge_db.query(KnowledgeProduct).filter(KnowledgeProduct.vertical_id == vertical_id).count(),
    )


def _knowledge_validated_brand_names(knowledge_id: int) -> Set[str]:
    with knowledge_session() as knowledge_db:
        return _knowledge_name_set(knowledge_db, KnowledgeBrand, knowledge_id)


def _legacy_validated_brand_names(db: Session, vertical_id: int) -> Set[str]:
    return _legacy_name_set(db, CanonicalBrand, vertical_id)


def _knowledge_name_set(knowledge_db: Session, model, vertical_id: int) -> Set[str]:
    rows = knowledge_db.query(model.canonical_name).filter(
        model.vertical_id == vertical_id,
        model.is_validated == True,
    ).all()
    return {name.casefold() for (name,) in rows if name}


def _legacy_name_set(db: Session, model, vertical_id: int) -> Set[str]:
    rows = db.query(model.canonical_name).filter(
        model.vertical_id == vertical_id,
        model.is_validated == True,
    ).all()
    return {name.casefold() for (name,) in rows if name}


def _upsert_knowledge_brand(
    db: Session,
    vertical_id: int,
    name: str,
    mention_count: int,
    source: Optional[str],
) -> KnowledgeBrand | None:
    clean = _clean_name(name)
    knowledge_id = _ensure_knowledge_vertical_id(db, vertical_id)
    if not knowledge_id or not clean:
        return None
    with knowledge_session() as knowledge_db:
        brand = _find_knowledge_brand(knowledge_db, knowledge_id, clean)
        return _save_knowledge_brand(knowledge_db, brand, knowledge_id, clean, mention_count, source)


def _upsert_knowledge_product(
    db: Session,
    vertical_id: int,
    brand_id: int | None,
    name: str,
    mention_count: int,
    source: Optional[str],
) -> KnowledgeProduct | None:
    clean = _clean_name(name)
    knowledge_id = _ensure_knowledge_vertical_id(db, vertical_id)
    if not knowledge_id or not clean:
        return None
    with knowledge_session() as knowledge_db:
        product = _find_knowledge_product(knowledge_db, knowledge_id, clean)
        return _save_knowledge_product(knowledge_db, product, knowledge_id, brand_id, clean, mention_count, source)


def _mark_knowledge_brand_validated(
    db: Session,
    vertical_id: int,
    name: str,
    source: str,
) -> None:
    _upsert_knowledge_brand(db, vertical_id, name, 0, source)


def _mark_knowledge_product_validated(
    db: Session,
    vertical_id: int,
    name: str,
    source: str,
) -> None:
    _upsert_knowledge_product(db, vertical_id, None, name, 0, source)


def _find_knowledge_brand(
    knowledge_db: Session,
    vertical_id: int,
    name: str,
) -> KnowledgeBrand | None:
    return knowledge_db.query(KnowledgeBrand).filter(
        KnowledgeBrand.vertical_id == vertical_id,
        func.lower(KnowledgeBrand.canonical_name) == name.casefold(),
    ).first()


def _find_knowledge_product(
    knowledge_db: Session,
    vertical_id: int,
    name: str,
) -> KnowledgeProduct | None:
    return knowledge_db.query(KnowledgeProduct).filter(
        KnowledgeProduct.vertical_id == vertical_id,
        func.lower(KnowledgeProduct.canonical_name) == name.casefold(),
    ).first()


def _save_knowledge_brand(
    knowledge_db: Session,
    brand: KnowledgeBrand | None,
    vertical_id: int,
    name: str,
    mention_count: int,
    source: Optional[str],
) -> KnowledgeBrand:
    if brand:
        _update_knowledge_brand(brand, mention_count, source)
        return brand
    return _create_knowledge_brand(knowledge_db, vertical_id, name, mention_count, source)


def _save_knowledge_product(
    knowledge_db: Session,
    product: KnowledgeProduct | None,
    vertical_id: int,
    brand_id: int | None,
    name: str,
    mention_count: int,
    source: Optional[str],
) -> KnowledgeProduct:
    if product:
        _update_knowledge_product(product, brand_id, mention_count, source)
        return product
    return _create_knowledge_product(knowledge_db, vertical_id, brand_id, name, mention_count, source)


def _update_knowledge_brand(
    brand: KnowledgeBrand,
    mention_count: int,
    source: Optional[str],
) -> None:
    brand.mention_count += mention_count
    _apply_validation(brand, mention_count, source)


def _update_knowledge_product(
    product: KnowledgeProduct,
    brand_id: int | None,
    mention_count: int,
    source: Optional[str],
) -> None:
    product.mention_count += mention_count
    if brand_id:
        product.brand_id = brand_id
    _apply_validation(product, mention_count, source)


def _create_knowledge_brand(
    knowledge_db: Session,
    vertical_id: int,
    name: str,
    mention_count: int,
    source: Optional[str],
) -> KnowledgeBrand:
    brand = KnowledgeBrand(
        vertical_id=vertical_id,
        canonical_name=name,
        display_name=name,
        mention_count=mention_count,
        is_validated=_is_validated(mention_count, source),
        validation_source=_validation_source(mention_count, source),
    )
    knowledge_db.add(brand)
    knowledge_db.flush()
    return brand


def _create_knowledge_product(
    knowledge_db: Session,
    vertical_id: int,
    brand_id: int | None,
    name: str,
    mention_count: int,
    source: Optional[str],
) -> KnowledgeProduct:
    product = KnowledgeProduct(
        vertical_id=vertical_id,
        brand_id=brand_id,
        canonical_name=name,
        display_name=name,
        mention_count=mention_count,
        is_validated=_is_validated(mention_count, source),
        validation_source=_validation_source(mention_count, source),
    )
    knowledge_db.add(product)
    knowledge_db.flush()
    return product


def _apply_validation(entity, mention_count: int, source: Optional[str]) -> None:
    if source:
        entity.is_validated = True
        entity.validation_source = source
        return
    if _is_validated(mention_count, source):
        entity.is_validated = True
        entity.validation_source = "auto"


def _is_validated(mention_count: int, source: Optional[str]) -> bool:
    return bool(source) or mention_count >= MIN_MENTION_COUNT_FOR_AUTO_VALIDATE


def _validation_source(mention_count: int, source: Optional[str]) -> Optional[str]:
    if source:
        return source
    return "auto" if mention_count >= MIN_MENTION_COUNT_FOR_AUTO_VALIDATE else None


def _add_knowledge_brand_alias(
    db: Session,
    vertical_id: int,
    canonical_id: int,
    alias_name: str,
) -> None:
    name = _legacy_brand_name(db, canonical_id)
    if name:
        _add_knowledge_brand_alias_by_name(db, vertical_id, name, alias_name)


def _add_knowledge_product_alias(
    db: Session,
    vertical_id: int,
    canonical_id: int,
    alias_name: str,
) -> None:
    name = _legacy_product_name(db, canonical_id)
    if name:
        _add_knowledge_product_alias_by_name(db, vertical_id, name, alias_name)


def _legacy_brand_name(db: Session, canonical_id: int) -> str:
    canonical = db.query(CanonicalBrand).filter(CanonicalBrand.id == canonical_id).first()
    return canonical.canonical_name if canonical else ""


def _legacy_product_name(db: Session, canonical_id: int) -> str:
    canonical = db.query(CanonicalProduct).filter(CanonicalProduct.id == canonical_id).first()
    return canonical.canonical_name if canonical else ""


def _add_knowledge_brand_alias_by_name(
    db: Session,
    vertical_id: int,
    canonical_name: str,
    alias_name: str,
) -> None:
    knowledge_id = _ensure_knowledge_vertical_id(db, vertical_id)
    if not knowledge_id:
        return
    with knowledge_session() as knowledge_db:
        brand = _find_knowledge_brand(knowledge_db, knowledge_id, canonical_name)
        if not brand:
            return
        if _knowledge_brand_alias_exists(knowledge_db, brand.id, alias_name):
            return
        _create_knowledge_brand_alias(knowledge_db, brand.id, alias_name)


def _add_knowledge_product_alias_by_name(
    db: Session,
    vertical_id: int,
    canonical_name: str,
    alias_name: str,
) -> None:
    knowledge_id = _ensure_knowledge_vertical_id(db, vertical_id)
    if not knowledge_id:
        return
    with knowledge_session() as knowledge_db:
        product = _find_knowledge_product(knowledge_db, knowledge_id, canonical_name)
        if not product:
            return
        if _knowledge_product_alias_exists(knowledge_db, product.id, alias_name):
            return
        _create_knowledge_product_alias(knowledge_db, product.id, alias_name)


def _knowledge_brand_alias_exists(knowledge_db: Session, brand_id: int, alias_name: str) -> bool:
    return bool(knowledge_db.query(KnowledgeBrandAlias).filter(
        KnowledgeBrandAlias.brand_id == brand_id,
        KnowledgeBrandAlias.alias == alias_name,
    ).first())


def _knowledge_product_alias_exists(knowledge_db: Session, product_id: int, alias_name: str) -> bool:
    return bool(knowledge_db.query(KnowledgeProductAlias).filter(
        KnowledgeProductAlias.product_id == product_id,
        KnowledgeProductAlias.alias == alias_name,
    ).first())


def _create_knowledge_brand_alias(knowledge_db: Session, brand_id: int, alias_name: str) -> None:
    knowledge_db.add(KnowledgeBrandAlias(brand_id=brand_id, alias=alias_name))
    knowledge_db.flush()


def _create_knowledge_product_alias(knowledge_db: Session, product_id: int, alias_name: str) -> None:
    knowledge_db.add(KnowledgeProductAlias(product_id=product_id, alias=alias_name))
    knowledge_db.flush()


def _add_knowledge_rejection(
    db: Session,
    vertical_id: int,
    entity_type: EntityType,
    name: str,
    reason: Optional[str],
) -> None:
    knowledge_id = _ensure_knowledge_vertical_id(db, vertical_id)
    if not knowledge_id:
        return
    with knowledge_session() as knowledge_db:
        if _knowledge_rejection_exists(knowledge_db, knowledge_id, entity_type, name):
            return
        knowledge_db.add(_knowledge_rejection(knowledge_id, entity_type, name, reason))
        knowledge_db.flush()


def _knowledge_rejection_exists(
    knowledge_db: Session,
    vertical_id: int,
    entity_type: EntityType,
    name: str,
) -> bool:
    return bool(knowledge_db.query(KnowledgeRejectedEntity).filter(
        KnowledgeRejectedEntity.vertical_id == vertical_id,
        KnowledgeRejectedEntity.entity_type == entity_type,
        func.lower(KnowledgeRejectedEntity.name) == name.casefold(),
    ).first())


def _knowledge_rejection(
    vertical_id: int,
    entity_type: EntityType,
    name: str,
    reason: Optional[str],
) -> KnowledgeRejectedEntity:
    return KnowledgeRejectedEntity(
        vertical_id=vertical_id,
        entity_type=entity_type,
        name=name,
        reason=reason or "user_reject",
    )


def _knowledge_brands_or_legacy(db: Session, vertical_id: int) -> List[object]:
    knowledge_id = _knowledge_vertical_id(db, vertical_id)
    if not knowledge_id:
        return _legacy_canonical_brands(db, vertical_id)
    with knowledge_session() as knowledge_db:
        brands = _knowledge_brands(knowledge_db, knowledge_id)
        return brands or _legacy_canonical_brands(db, vertical_id)


def _knowledge_products_or_legacy(db: Session, vertical_id: int) -> List[object]:
    knowledge_id = _knowledge_vertical_id(db, vertical_id)
    if not knowledge_id:
        return _legacy_canonical_products(db, vertical_id)
    with knowledge_session() as knowledge_db:
        products = _knowledge_products(knowledge_db, knowledge_id)
        return products or _legacy_canonical_products(db, vertical_id)


def _legacy_canonical_brands(db: Session, vertical_id: int) -> List[CanonicalBrand]:
    return db.query(CanonicalBrand).filter(
        CanonicalBrand.vertical_id == vertical_id
    ).order_by(CanonicalBrand.mention_count.desc()).all()


def _legacy_canonical_products(db: Session, vertical_id: int) -> List[CanonicalProduct]:
    return db.query(CanonicalProduct).filter(
        CanonicalProduct.vertical_id == vertical_id
    ).order_by(CanonicalProduct.mention_count.desc()).all()


def _knowledge_brands(knowledge_db: Session, vertical_id: int) -> List[KnowledgeBrand]:
    return knowledge_db.query(KnowledgeBrand).options(
        joinedload(KnowledgeBrand.aliases)
    ).filter(
        KnowledgeBrand.vertical_id == vertical_id
    ).order_by(KnowledgeBrand.mention_count.desc()).all()


def _knowledge_products(knowledge_db: Session, vertical_id: int) -> List[KnowledgeProduct]:
    return knowledge_db.query(KnowledgeProduct).options(
        joinedload(KnowledgeProduct.aliases)
    ).filter(
        KnowledgeProduct.vertical_id == vertical_id
    ).order_by(KnowledgeProduct.mention_count.desc()).all()


def _clean_name(value: str) -> str:
    return (value or "").strip()
