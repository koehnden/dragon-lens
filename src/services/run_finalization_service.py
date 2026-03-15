import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from config import settings
from models import Brand, BrandMention, LLMAnswer, Product, ProductMention, Run, Vertical
from models.db_retry import commit_with_retry
from models.domain import RunStatus
from services.brand_recognition.async_utils import _run_async
from services.brand_recognition.consolidation_service import run_enhanced_consolidation
from services.brand_recognition.product_brand_mapping import (
    map_products_to_brands_for_run,
)
from services.brand_recognition.vertical_gate import apply_vertical_gate_to_run
from services.entity_consolidation import consolidate_run
from services.metrics_service import calculate_and_save_metrics
from services.product_metrics_service import calculate_and_save_run_product_metrics
from services.translater import (
    TranslaterService,
    extract_chinese_part,
    extract_english_part,
    has_chinese_characters,
    has_latin_letters,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FinalizeTaskResult:
    run_id: int
    status: str
    failed_count: int
    failed_prompt_ids: list[int]

    def to_payload(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "failed_count": self.failed_count,
            "failed_prompt_ids": self.failed_prompt_ids,
        }


def finalize_run_processing(
    db: Session,
    run_id: int,
    results: list[dict],
    force_reextract: bool = False,
    skip_entity_consolidation: bool = False,
) -> FinalizeTaskResult:
    del force_reextract

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    failed_ids = failed_prompt_ids(results)
    if should_fail_run(results):
        run.status = RunStatus.FAILED
        run.error_message = (
            f"Run failed: failed_prompts={len(failed_ids)} prompt_ids={failed_ids}"
        )
        run.completed_at = datetime.utcnow()
        commit_with_retry(db)
        return FinalizeTaskResult(run_id, "failed", len(failed_ids), failed_ids)

    backfill_entity_english_names(db, run)

    enhanced_result = _run_async(run_enhanced_consolidation(db, run_id))
    _run_async(apply_vertical_gate_to_run(db, run_id))
    if not skip_entity_consolidation:
        consolidate_run(db, run_id, normalized_brands=enhanced_result.normalized_brands)
    _run_async(map_products_to_brands_for_run(db, run_id))
    calculate_and_save_metrics(db, run_id)
    calculate_and_save_run_product_metrics(db, run_id)
    run_comparison_if_enabled(db, run_id)

    if settings.vertical_auto_match_enabled:
        try:
            from services.vertical_auto_match import ensure_vertical_grouping_for_run

            _run_async(ensure_vertical_grouping_for_run(db, run_id))
        except Exception as exc:
            logger.warning("Vertical auto-match skipped for run %s: %s", run_id, exc)

    run.status = RunStatus.COMPLETED
    run.completed_at = datetime.utcnow()
    if failed_ids:
        run.error_message = (
            f"Completed with warnings: failed_prompts={len(failed_ids)} "
            f"prompt_ids={failed_ids}"
        )
    commit_with_retry(db)
    return FinalizeTaskResult(run_id, "completed", len(failed_ids), failed_ids)


def failed_prompt_ids(results: list[dict]) -> list[int]:
    return [int(r.get("prompt_id")) for r in results if not r.get("ok")]


def should_fail_run(results: list[dict]) -> bool:
    total = max(1, len(results))
    failed = len(failed_prompt_ids(results))
    if failed == 0:
        return False
    if failed > settings.fail_if_failed_prompts_gt:
        return True
    return failed / total > settings.fail_if_failed_rate_gt


def run_comparison_if_enabled(db: Session, run_id: int) -> None:
    from models import ComparisonRunStatus, RunComparisonConfig
    from services.comparison_prompts.metrics_update import (
        update_run_metrics_with_comparison_sentiment,
    )
    from services.comparison_prompts.run_pipeline import run_comparison_pipeline

    config = (
        db.query(RunComparisonConfig)
        .filter(RunComparisonConfig.run_id == run_id)
        .first()
    )
    if not config or not config.enabled:
        return
    try:
        _run_async(run_comparison_pipeline(db, run_id))
        update_run_metrics_with_comparison_sentiment(db, run_id)
    except Exception as exc:
        logger.error(
            "Comparison pipeline failed for run %s: %s", run_id, exc, exc_info=True
        )
        config.status = ComparisonRunStatus.FAILED
        config.error_message = str(exc)
        config.completed_at = datetime.utcnow()
        commit_with_retry(db)


def mentioned_brand_ids(db: Session, run_id: int) -> list[int]:
    rows = (
        db.query(BrandMention.brand_id)
        .join(LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id, BrandMention.mentioned)
        .distinct()
        .all()
    )
    return [int(r[0]) for r in rows]


def mentioned_product_ids(db: Session, run_id: int) -> list[int]:
    rows = (
        db.query(ProductMention.product_id)
        .join(LLMAnswer, LLMAnswer.id == ProductMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id, ProductMention.mentioned)
        .distinct()
        .all()
    )
    return [int(r[0]) for r in rows]


def normalize_mixed_original_name(name: str) -> tuple[str, str]:
    english = extract_english_part(name)
    chinese = extract_chinese_part(name)
    return english.strip(), chinese.strip()


def append_alias(aliases: dict, lang: str, value: str) -> dict:
    aliases = aliases or {"zh": [], "en": []}
    aliases.setdefault("zh", [])
    aliases.setdefault("en", [])
    if value and value not in aliases[lang]:
        aliases[lang].append(value)
    return aliases


def backfill_entity_english_names(db: Session, run: Run) -> None:
    vertical = db.query(Vertical).filter(Vertical.id == run.vertical_id).first()
    if not vertical:
        return
    brands = db.query(Brand).filter(Brand.id.in_(mentioned_brand_ids(db, run.id))).all()
    products = (
        db.query(Product)
        .filter(Product.id.in_(mentioned_product_ids(db, run.id)))
        .all()
    )
    translator = TranslaterService()
    normalize_run_entities(brands, products)
    items = entities_missing_english(brands, products)
    if items:
        mapping = _run_async(
            translator.translate_entities_to_english_batch(
                items, vertical.name, vertical.description
            )
        )
        apply_entity_english_mapping(brands, products, mapping)
    commit_with_retry(db)


def normalize_run_entities(brands: list[Brand], products: list[Product]) -> None:
    for brand in brands:
        if has_latin_letters(brand.original_name) and has_chinese_characters(
            brand.original_name
        ):
            english, chinese = normalize_mixed_original_name(brand.original_name)
            if english:
                brand.original_name = english
                brand.translated_name = None
            if chinese:
                brand.aliases = append_alias(brand.aliases, "zh", chinese)
            if english:
                brand.aliases = append_alias(brand.aliases, "en", english)
    for product in products:
        if has_latin_letters(product.original_name) and has_chinese_characters(
            product.original_name
        ):
            english, _ = normalize_mixed_original_name(product.original_name)
            if english:
                product.original_name = english
                product.translated_name = None


def entities_missing_english(brands: list[Brand], products: list[Product]) -> list[dict]:
    items: list[dict] = []
    for brand in brands:
        if brand.translated_name:
            continue
        if has_chinese_characters(brand.original_name) and not has_latin_letters(
            brand.original_name
        ):
            items.append({"type": "brand", "name": brand.original_name.strip()})
    for product in products:
        if product.translated_name:
            continue
        if has_chinese_characters(product.original_name) and not has_latin_letters(
            product.original_name
        ):
            items.append({"type": "product", "name": product.original_name.strip()})
    return items


def apply_entity_english_mapping(
    brands: list[Brand],
    products: list[Product],
    mapping: dict[tuple[str, str], str],
) -> None:
    for brand in brands:
        key = ("brand", (brand.original_name or "").strip())
        english = mapping.get(key)
        if not english:
            continue
        brand.translated_name = english
        brand.aliases = append_alias(brand.aliases, "en", english)
    for product in products:
        key = ("product", (product.original_name or "").strip())
        english = mapping.get(key)
        if not english:
            continue
        product.translated_name = english
