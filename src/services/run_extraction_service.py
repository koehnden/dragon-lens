import json
import logging
from dataclasses import dataclass

from sqlalchemy.orm import Session

from config import settings
from models import (
    Brand,
    BrandMention,
    ExtractionDebug,
    LLMAnswer,
    Product,
    ProductMention,
    Run,
    Vertical,
)
from models.db_retry import commit_with_retry, flush_with_retry
from models.domain import Sentiment
from services.brand_discovery import discover_brands_and_products
from services.brand_recognition.async_utils import _run_async
from services.product_discovery import discover_and_store_products
from services.translater import TranslaterService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExtractionTaskResult:
    ok: bool
    stage: str
    error: str | None = None

    def to_payload(self, payload: dict) -> dict:
        return {**payload, "ok": self.ok, "stage": self.stage, "error": self.error}


def extract_mentions_for_answer(
    db: Session, run_id: int, llm_answer_id: int, force_reextract: bool = False
) -> ExtractionTaskResult:
    try:
        answer = db.query(LLMAnswer).filter(LLMAnswer.id == llm_answer_id).first()
        run = db.query(Run).filter(Run.id == run_id).first()
        if not answer or not run:
            return ExtractionTaskResult(False, "extraction", "Run or answer not found")

        if not force_reextract and has_mentions(db, llm_answer_id):
            return ExtractionTaskResult(True, "extraction_skipped", None)

        db.query(BrandMention).filter(BrandMention.llm_answer_id == llm_answer_id).delete()
        db.query(ProductMention).filter(
            ProductMention.llm_answer_id == llm_answer_id
        ).delete()
        flush_with_retry(db)

        brands = db.query(Brand).filter(Brand.vertical_id == run.vertical_id).all()
        translator = TranslaterService()
        from services.ollama import OllamaService
        from services.translation_feedback import apply_translation_feedback

        ollama_service = OllamaService()
        answer_zh = answer.raw_answer_zh or ""
        logger.info(
            "[TASK] ensure_extraction: calling discover_brands_and_products for run=%s",
            run_id,
        )
        all_brands, extraction_result = discover_brands_and_products(
            answer_zh, run.vertical_id, brands, db
        )
        logger.info(
            "[TASK] ensure_extraction: discover_brands_and_products completed, %s brands found",
            len(all_brands),
        )

        if extraction_result.debug_info:
            logger.info("[TASK] ensure_extraction: storing extraction debug info")
            store_extraction_debug(db, llm_answer_id, extraction_result.debug_info)
            logger.info("[TASK] ensure_extraction: debug record added")

        logger.info("[TASK] ensure_extraction: calling discover_and_store_products")
        discovered_products = discover_and_store_products(
            db,
            run.vertical_id,
            answer_zh,
            all_brands,
            extraction_relationships=extraction_result.product_brand_relationships,
        )
        logger.info(
            "[TASK] ensure_extraction: discover_and_store_products completed, %s products",
            len(discovered_products),
        )

        vertical = db.query(Vertical).filter(Vertical.id == run.vertical_id).first()
        vertical_name = vertical.name if vertical else ""
        vertical_description = vertical.description if vertical else None
        apply_translation_feedback(
            db,
            vertical_name=vertical_name,
            vertical_description=vertical_description,
            brands=all_brands,
            products=discovered_products,
        )

        brand_names = [b.display_name for b in all_brands]
        brand_aliases = [
            b.aliases.get("zh", []) + b.aliases.get("en", []) for b in all_brands
        ]
        brand_mentions = _run_async(
            ollama_service.extract_brands(answer_zh, brand_names, brand_aliases)
        )

        product_names, product_aliases = products_to_variants(discovered_products)
        brand_names_for_products, brand_aliases_for_products = brands_to_variants(
            all_brands
        )
        product_mentions = _run_async(
            ollama_service.extract_products(
                answer_zh,
                product_names,
                product_aliases,
                brand_names_for_products,
                brand_aliases_for_products,
            )
        )

        all_snippets, snippet_map = collect_all_snippets(brand_mentions, product_mentions)
        if settings.batch_translation_enabled and all_snippets:
            translated = translator.translate_batch_sync(
                all_snippets, "Chinese", "English"
            )
        else:
            translated = [
                translator.translate_text_sync(s, "Chinese", "English")
                for s in all_snippets
            ]

        for mention_data in brand_mentions:
            if not mention_data["mentioned"]:
                continue
            brand = all_brands[mention_data["brand_index"]]
            sentiment_str = "neutral"
            if mention_data["snippets"]:
                sentiment_str = _run_async(
                    ollama_service.classify_sentiment(mention_data["snippets"][0])
                )
            sentiment = map_sentiment(sentiment_str)
            en_snippets = get_translated_snippets(
                "brand",
                mention_data["brand_index"],
                mention_data["snippets"],
                snippet_map,
                translated,
            )
            db.add(
                BrandMention(
                    llm_answer_id=llm_answer_id,
                    brand_id=brand.id,
                    mentioned=True,
                    rank=mention_data["rank"],
                    sentiment=sentiment,
                    evidence_snippets={
                        "zh": mention_data["snippets"],
                        "en": en_snippets,
                    },
                )
            )

        for mention_data in product_mentions:
            if not mention_data["mentioned"] or mention_data["rank"] is None:
                continue
            product = discovered_products[mention_data["product_index"]]
            sentiment_str = "neutral"
            if mention_data["snippets"]:
                sentiment_str = _run_async(
                    ollama_service.classify_sentiment(mention_data["snippets"][0])
                )
            sentiment = map_sentiment(sentiment_str)
            en_snippets = get_translated_snippets(
                "product",
                mention_data["product_index"],
                mention_data["snippets"],
                snippet_map,
                translated,
            )
            db.add(
                ProductMention(
                    llm_answer_id=llm_answer_id,
                    product_id=product.id,
                    mentioned=True,
                    rank=mention_data["rank"],
                    sentiment=sentiment,
                    evidence_snippets={
                        "zh": mention_data["snippets"],
                        "en": en_snippets,
                    },
                )
            )

        flush_with_retry(db)
        commit_with_retry(db)
        return ExtractionTaskResult(True, "extraction", None)
    except Exception as exc:
        logger.error(
            "ensure_extraction failed for run=%s llm_answer=%s: %s",
            run_id,
            llm_answer_id,
            exc,
            exc_info=True,
        )
        return ExtractionTaskResult(False, "extraction", str(exc))


def has_mentions(db: Session, llm_answer_id: int) -> bool:
    if (
        db.query(BrandMention.id)
        .filter(BrandMention.llm_answer_id == llm_answer_id)
        .first()
    ):
        return True
    return (
        db.query(ProductMention.id)
        .filter(ProductMention.llm_answer_id == llm_answer_id)
        .first()
        is not None
    )


def store_extraction_debug(db: Session, llm_answer_id: int, debug_info) -> None:
    db.query(ExtractionDebug).filter(
        ExtractionDebug.llm_answer_id == llm_answer_id
    ).delete()
    debug_record = ExtractionDebug(
        llm_answer_id=llm_answer_id,
        raw_brands=json.dumps(debug_info.raw_brands, ensure_ascii=False),
        raw_products=json.dumps(debug_info.raw_products, ensure_ascii=False),
        rejected_at_light_filter=json.dumps(
            debug_info.rejected_at_light_filter, ensure_ascii=False
        ),
        final_brands=json.dumps(debug_info.final_brands, ensure_ascii=False),
        final_products=json.dumps(debug_info.final_products, ensure_ascii=False),
        extraction_method="qwen",
    )
    db.add(debug_record)


def map_sentiment(sentiment_str: str) -> Sentiment:
    if sentiment_str == "positive":
        return Sentiment.POSITIVE
    if sentiment_str == "negative":
        return Sentiment.NEGATIVE
    return Sentiment.NEUTRAL


def create_product_mentions(
    db: Session,
    llm_answer: LLMAnswer,
    products: list[Product],
    answer_zh: str,
    translator: TranslaterService,
    brands: list[Brand],
    ollama_service,
) -> None:
    product_names, product_aliases = products_to_variants(products)
    brand_names, brand_aliases = brands_to_variants(brands)
    mentions = _run_async(
        ollama_service.extract_products(
            answer_zh, product_names, product_aliases, brand_names, brand_aliases
        )
    )
    for mention_data in mentions:
        if not mention_data["mentioned"]:
            continue
        rank = mention_data["rank"]
        if rank is None:
            continue

        product = products[mention_data["product_index"]]
        sentiment_str = "neutral"
        if mention_data["snippets"]:
            sentiment_str = _run_async(
                ollama_service.classify_sentiment(mention_data["snippets"][0])
            )
        sentiment = map_sentiment(sentiment_str)
        en_snippets = [
            translator.translate_text_sync(snippet, "Chinese", "English")
            for snippet in mention_data["snippets"]
        ]

        db.add(
            ProductMention(
                llm_answer_id=llm_answer.id,
                product_id=product.id,
                mentioned=True,
                rank=rank,
                sentiment=sentiment,
                evidence_snippets={"zh": mention_data["snippets"], "en": en_snippets},
            )
        )
    flush_with_retry(db)


def products_to_variants(products: list[Product]) -> tuple[list[str], list[list[str]]]:
    names = []
    aliases = []
    for product in products:
        variants = product_variants(product)
        names.append(variants[0] if variants else product.display_name)
        aliases.append(variants[1:] if len(variants) > 1 else [])
    return names, aliases


def brands_to_variants(brands: list[Brand]) -> tuple[list[str], list[list[str]]]:
    names = []
    aliases = []
    for brand in brands:
        names.append(brand.display_name)
        aliases.append(brand_aliases(brand))
    return names, aliases


def brand_aliases(brand: Brand) -> list[str]:
    variants = [brand.original_name or "", brand.translated_name or ""]
    variants.extend((brand.aliases or {}).get("zh", []))
    variants.extend((brand.aliases or {}).get("en", []))
    return [variant for variant in variants if variant]


def product_variants(product: Product) -> list[str]:
    variants = [
        product.display_name,
        product.original_name,
        product.translated_name or "",
    ]
    seen: set[str] = set()
    result: list[str] = []
    for variant in variants:
        if not variant or variant in seen:
            continue
        seen.add(variant)
        result.append(variant)
    return result


def collect_all_snippets(
    brand_mentions: list[dict],
    product_mentions: list[dict],
) -> tuple[list[str], dict[tuple[str, int, int], int]]:
    all_snippets: list[str] = []
    snippet_map: dict[tuple[str, int, int], int] = {}
    for mention_data in brand_mentions:
        if not mention_data.get("mentioned"):
            continue
        brand_idx = mention_data["brand_index"]
        for j, snippet in enumerate(mention_data.get("snippets", [])):
            snippet_map[("brand", brand_idx, j)] = len(all_snippets)
            all_snippets.append(snippet)
    for mention_data in product_mentions:
        if not mention_data.get("mentioned") or mention_data.get("rank") is None:
            continue
        product_idx = mention_data["product_index"]
        for j, snippet in enumerate(mention_data.get("snippets", [])):
            snippet_map[("product", product_idx, j)] = len(all_snippets)
            all_snippets.append(snippet)
    return all_snippets, snippet_map


def get_translated_snippets(
    entity_type: str,
    entity_idx: int,
    zh_snippets: list[str],
    snippet_map: dict[tuple[str, int, int], int],
    translated: list[str],
) -> list[str]:
    en_snippets = []
    for j in range(len(zh_snippets)):
        pos = snippet_map.get((entity_type, entity_idx, j))
        if pos is not None and pos < len(translated):
            en_snippets.append(translated[pos])
        else:
            en_snippets.append(zh_snippets[j])
    return en_snippets
