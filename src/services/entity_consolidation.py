import logging
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

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


def consolidate_run(db: Session, run_id: int) -> ConsolidationResult:
    logger.info(f"Starting entity consolidation for run {run_id}")

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    vertical_id = run.vertical_id

    brand_mentions = _collect_brand_mentions(db, run_id)
    product_mentions = _collect_product_mentions(db, run_id)

    brand_merge_candidates = find_merge_candidates(
        list(brand_mentions.keys()), EntityType.BRAND
    )
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

    canonical_brands = db.query(CanonicalBrand).filter(
        CanonicalBrand.vertical_id == vertical_id
    ).count()
    canonical_products = db.query(CanonicalProduct).filter(
        CanonicalProduct.vertical_id == vertical_id
    ).count()

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
    name = name.lower().strip()
    name = re.sub(r'[\s\-_]+', '', name)
    name = re.sub(r'[（）\(\)]', '', name)
    return name


def _calculate_similarity(name1: str, name2: str) -> float:
    if name1 == name2:
        return 1.0

    if name1 in name2 or name2 in name1:
        shorter = min(len(name1), len(name2))
        longer = max(len(name1), len(name2))
        return shorter / longer if longer > 0 else 0.0

    return SequenceMatcher(None, name1, name2).ratio()


def _determine_canonical(name1: str, name2: str) -> Tuple[str, str]:
    if len(name1) > len(name2):
        return name1, name2
    if len(name2) > len(name1):
        return name2, name1

    has_english1 = bool(re.search(r'[A-Za-z]', name1))
    has_english2 = bool(re.search(r'[A-Za-z]', name2))
    if has_english1 and not has_english2:
        return name1, name2
    if has_english2 and not has_english1:
        return name2, name1

    return (name1, name2) if name1 < name2 else (name2, name1)


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
            _add_brand_alias(db, canonical.id, source_name)
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
            _add_product_alias(db, canonical.id, source_name)
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


def _add_brand_alias(db: Session, canonical_id: int, alias_name: str) -> None:
    existing = db.query(BrandAlias).filter(
        BrandAlias.canonical_brand_id == canonical_id,
        BrandAlias.alias == alias_name,
    ).first()

    if not existing:
        alias = BrandAlias(canonical_brand_id=canonical_id, alias=alias_name)
        db.add(alias)


def _add_product_alias(db: Session, canonical_id: int, alias_name: str) -> None:
    existing = db.query(ProductAlias).filter(
        ProductAlias.canonical_product_id == canonical_id,
        ProductAlias.alias == alias_name,
    ).first()

    if not existing:
        alias = ProductAlias(canonical_product_id=canonical_id, alias=alias_name)
        db.add(alias)


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
        else:
            _get_or_create_canonical_product(
                db, candidate.vertical_id, candidate.name, candidate.mention_count
            )
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


def get_canonical_brands(db: Session, vertical_id: int) -> List[CanonicalBrand]:
    return db.query(CanonicalBrand).filter(
        CanonicalBrand.vertical_id == vertical_id
    ).order_by(CanonicalBrand.mention_count.desc()).all()


def get_canonical_products(db: Session, vertical_id: int) -> List[CanonicalProduct]:
    return db.query(CanonicalProduct).filter(
        CanonicalProduct.vertical_id == vertical_id
    ).order_by(CanonicalProduct.mention_count.desc()).all()
