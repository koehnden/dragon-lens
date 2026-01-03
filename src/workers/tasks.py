import asyncio
import logging
from datetime import datetime
from typing import List

from celery import Task
from sqlalchemy.orm import Session

import json

from models import (
    Brand,
    BrandMention,
    ExtractionDebug,
    LLMAnswer,
    Product,
    ProductMention,
    Prompt,
    Run,
    Vertical,
)
from models.database import SessionLocal
from models.domain import PromptLanguage, RunStatus, Sentiment
from models.db_retry import commit_with_retry, flush_with_retry
from services.answer_reuse import find_reusable_answer
from services.brand_discovery import discover_brands_and_products
from services.brand_recognition import extract_entities
from services.entity_consolidation import consolidate_run
from services.brand_recognition.consolidation_service import run_enhanced_consolidation
from services.brand_recognition.vertical_gate import apply_vertical_gate_to_run
from services.product_discovery import discover_and_store_products
from services.translater import TranslaterService
from services.metrics_service import calculate_and_save_metrics
from services.pricing import calculate_cost
from services.remote_llms import LLMRouter
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

_persistent_event_loop = None


def _get_or_create_event_loop():
    global _persistent_event_loop
    if _persistent_event_loop is None or _persistent_event_loop.is_closed():
        _persistent_event_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_persistent_event_loop)
    return _persistent_event_loop


def _run_async(coro):
    loop = _get_or_create_event_loop()
    return loop.run_until_complete(coro)


class DatabaseTask(Task):
    _db: Session | None = None

    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


@celery_app.task(base=DatabaseTask, bind=True)
def run_vertical_analysis(self: DatabaseTask, vertical_id: int, provider: str, model_name: str, run_id: int):
    logger.info(f"Starting vertical analysis: vertical={vertical_id}, provider={provider}, model={model_name}, run={run_id}")

    try:
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not run:
            raise ValueError(f"Run {run_id} not found")

        run.status = RunStatus.IN_PROGRESS

        vertical = self.db.query(Vertical).filter(Vertical.id == vertical_id).first()
        if not vertical:
            raise ValueError(f"Vertical {vertical_id} not found")

        prompts = self.db.query(Prompt).filter(Prompt.run_id == run_id).all()
        if not prompts:
            raise ValueError(f"No prompts found for run {run_id}")

        brands = self.db.query(Brand).filter(Brand.vertical_id == vertical_id).all()
        if not brands:
            raise ValueError(f"No brands found for vertical {vertical_id}")

        llm_router = LLMRouter(self.db)
        resolution = llm_router.resolve(provider, model_name)
        run.route = resolution.route
        commit_with_retry(self.db)
        translator = TranslaterService()
        from services.ollama import OllamaService
        ollama_service = OllamaService()

        for prompt in prompts:
            logger.info(f"Processing prompt {prompt.id}")

            prompt_text_zh = prompt.text_zh
            prompt_text_en = prompt.text_en

            if not prompt_text_zh and prompt_text_en:
                logger.info(f"Translating English prompt to Chinese: {prompt_text_en[:50]}...")
                prompt_text_zh = translator.translate_text_sync(prompt_text_en, "English", "Chinese")
                logger.info(f"Translated to Chinese: {prompt_text_zh[:50]}...")

            if not prompt_text_zh:
                logger.warning(f"Prompt {prompt.id} has no text, skipping")
                continue

            existing_answer = (
                self.db.query(LLMAnswer)
                .filter(LLMAnswer.run_id == run_id, LLMAnswer.prompt_id == prompt.id)
                .first()
            )

            if existing_answer:
                logger.info(f"Found existing answer for prompt {prompt.id}, reusing for extraction")
                llm_answer = existing_answer
                answer_zh = existing_answer.raw_answer_zh

                self.db.query(BrandMention).filter(
                    BrandMention.llm_answer_id == existing_answer.id
                ).delete()
                self.db.query(ProductMention).filter(
                    ProductMention.llm_answer_id == existing_answer.id
                ).delete()
                flush_with_retry(self.db)

            else:
                reusable = find_reusable_answer(
                    self.db, run,
                    prompt_text_zh=prompt_text_zh,
                    prompt_text_en=prompt_text_en,
                )
                if reusable:
                    logger.info(f"Reusing answer from previous run for prompt {prompt.id}")
                    answer_zh = reusable.raw_answer_zh
                    answer_en = reusable.raw_answer_en
                    tokens_in = reusable.tokens_in
                    tokens_out = reusable.tokens_out
                    latency = reusable.latency
                    cost_estimate = reusable.cost_estimate
                else:
                    logger.info(f"Querying {provider}/{model_name} with prompt: {prompt_text_zh[:100]}...")
                    answer_zh, tokens_in, tokens_out, latency = _run_async(
                        llm_router.query_with_resolution(resolution, prompt_text_zh)
                    )
                    logger.info(f"Received answer: {answer_zh[:100]}...")

                    answer_en = None
                    if answer_zh:
                        logger.info("Translating answer to English...")
                        answer_en = translator.translate_text_sync(answer_zh, "Chinese", "English")
                        logger.info(f"Translated answer: {answer_en[:100]}...")

                    cost_estimate = calculate_cost(
                        provider,
                        model_name,
                        tokens_in,
                        tokens_out,
                        route=resolution.route,
                    )

                answer_route = resolution.route
                if reusable and reusable.route:
                    answer_route = reusable.route

                llm_answer = LLMAnswer(
                    run_id=run_id,
                    prompt_id=prompt.id,
                    provider=provider,
                    model_name=model_name,
                    route=answer_route,
                    raw_answer_zh=answer_zh,
                    raw_answer_en=answer_en,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency=latency,
                    cost_estimate=cost_estimate,
                )
                self.db.add(llm_answer)
                flush_with_retry(self.db)

            logger.info("Discovering all brands in response...")
            all_brands, extraction_result = discover_brands_and_products(
                answer_zh, vertical_id, brands, self.db
            )
            logger.info(
                f"Found {len(all_brands)} brands ({len(brands)} user-input, {len(all_brands) - len(brands)} discovered)"
            )

            if extraction_result.debug_info:
                debug_record = ExtractionDebug(
                    llm_answer_id=llm_answer.id,
                    raw_brands=json.dumps(extraction_result.debug_info.raw_brands, ensure_ascii=False),
                    raw_products=json.dumps(extraction_result.debug_info.raw_products, ensure_ascii=False),
                    rejected_at_light_filter=json.dumps(extraction_result.debug_info.rejected_at_light_filter, ensure_ascii=False),
                    final_brands=json.dumps(extraction_result.debug_info.final_brands, ensure_ascii=False),
                    final_products=json.dumps(extraction_result.debug_info.final_products, ensure_ascii=False),
                    extraction_method="qwen",
                )
                self.db.add(debug_record)

            logger.info("Discovering products in response...")
            discovered_products = discover_and_store_products(
                self.db, vertical_id, answer_zh, all_brands
            )
            logger.info(f"Found {len(discovered_products)} products")

            _create_product_mentions(
                self.db,
                llm_answer,
                discovered_products,
                answer_zh,
                translator,
                all_brands,
                ollama_service,
            )

            brand_names = [b.display_name for b in all_brands]
            brand_aliases = [b.aliases.get("zh", []) + b.aliases.get("en", []) for b in all_brands]

            logger.info(f"Extracting brand mentions for {len(all_brands)} brands...")
            mentions = _run_async(
                ollama_service.extract_brands(answer_zh, brand_names, brand_aliases)
            )

            for mention_data in mentions:
                if not mention_data["mentioned"]:
                    continue

                brand = all_brands[mention_data["brand_index"]]

                sentiment_str = "neutral"
                if mention_data["snippets"]:
                    snippet = mention_data["snippets"][0]
                    sentiment_str = _run_async(ollama_service.classify_sentiment(snippet))
                    logger.info(f"Brand {brand.display_name} sentiment: {sentiment_str}")

                sentiment = Sentiment.POSITIVE if sentiment_str == "positive" else (
                    Sentiment.NEGATIVE if sentiment_str == "negative" else Sentiment.NEUTRAL
                )

                en_snippets = []
                for snippet in mention_data["snippets"]:
                    en_snippet = translator.translate_text_sync(snippet, "Chinese", "English")
                    en_snippets.append(en_snippet)

                mention = BrandMention(
                    llm_answer_id=llm_answer.id,
                    brand_id=brand.id,
                    mentioned=True,
                    rank=mention_data["rank"],
                    sentiment=sentiment,
                    evidence_snippets={"zh": mention_data["snippets"], "en": en_snippets},
                )
                self.db.add(mention)

            commit_with_retry(self.db)

        logger.info(f"Running enhanced consolidation for run {run_id}...")
        enhanced_result = _run_async(run_enhanced_consolidation(self.db, run_id))
        logger.info(
            f"Enhanced consolidation complete: {len(enhanced_result.final_brands)} brands, "
            f"{len(enhanced_result.final_products)} products after normalization/validation"
        )

        logger.info(f"Applying off-vertical gate for discovered brands in run {run_id}...")
        rejected = _run_async(apply_vertical_gate_to_run(self.db, run_id))
        logger.info(f"Off-vertical gate rejected {rejected} discovered brands")

        logger.info(f"Consolidating entities for run {run_id}...")
        consolidation_result = consolidate_run(self.db, run_id, normalized_brands=enhanced_result.normalized_brands)
        logger.info(
            f"Entity consolidation complete: {consolidation_result.brands_merged} brands merged, "
            f"{consolidation_result.products_merged} products merged, "
            f"{consolidation_result.brands_flagged} brands flagged for review"
        )

        logger.info(f"Calculating metrics for run {run_id}...")
        calculate_and_save_metrics(self.db, run_id)
        logger.info(f"Metrics calculated and saved for run {run_id}")

        run.status = RunStatus.COMPLETED
        run.completed_at = datetime.utcnow()
        commit_with_retry(self.db)

        logger.info(f"Completed vertical analysis: run={run_id}")

    except Exception as e:
        logger.error(f"Error in vertical analysis: {e}", exc_info=True)

        run = self.db.query(Run).filter(Run.id == run_id).first()
        if run:
            run.status = RunStatus.FAILED
            run.error_message = str(e)
            run.completed_at = datetime.utcnow()
            commit_with_retry(self.db)

        raise


@celery_app.task
def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    logger.info(f"Translating from {source_lang} to {target_lang}")
    return f"[TODO: Translation of: {text}]"


@celery_app.task
def extract_brand_mentions(answer_text: str, brands: List[dict]) -> List[dict]:
    logger.info("Extracting brand mentions")
    if not brands:
        return []
    primary = brands[0]
    aliases = primary.get("aliases") or {"zh": [], "en": []}
    result = extract_entities(answer_text, primary.get("display_name", ""), aliases)
    mentions = []
    for name, surfaces in result.brands.items():
        mentions.append({"canonical": name, "mentions": surfaces})
    return mentions


@celery_app.task
def classify_sentiment(text: str) -> str:
    logger.info("Classifying sentiment")
    return "neutral"

def _detect_mentions(answer_text: str, brands: List[Brand]) -> dict[int, List[str]]:
    if not brands:
        return {}
    primary = brands[0]
    result = extract_entities(answer_text, primary.display_name, primary.aliases)
    mention_map: dict[int, List[str]] = {}
    for canonical_name, surfaces in result.brands.items():
        brand = _ensure_brand(primary.vertical_id, canonical_name, primary.aliases)
        mention_map[brand.id] = surfaces
    return mention_map


def _ensure_brand(vertical_id: int, canonical_name: str, aliases: dict) -> Brand:
    session = SessionLocal()
    brand = session.query(Brand).filter(Brand.vertical_id == vertical_id, Brand.display_name == canonical_name).first()
    brand = brand or Brand(
        vertical_id=vertical_id,
        display_name=canonical_name,
        original_name=canonical_name,
        translated_name=None,
        aliases=aliases or {"zh": [], "en": []},
    )
    if brand.id is None:
        session.add(brand)
        commit_with_retry(session)
        session.refresh(brand)
    session.close()
    return brand


def _map_sentiment(sentiment_str: str) -> Sentiment:
    if sentiment_str == "positive":
        return Sentiment.POSITIVE
    if sentiment_str == "negative":
        return Sentiment.NEGATIVE
    return Sentiment.NEUTRAL


def _create_product_mentions(
    db: Session,
    llm_answer: LLMAnswer,
    products: List[Product],
    answer_zh: str,
    translator: TranslaterService,
    brands: List[Brand],
    ollama_service,
) -> None:
    product_names, product_aliases = _products_to_variants(products)
    brand_names, brand_aliases = _brands_to_variants(brands)
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
            sentiment_str = _run_async(ollama_service.classify_sentiment(mention_data["snippets"][0]))
        sentiment = _map_sentiment(sentiment_str)

        en_snippets = []
        for snippet in mention_data["snippets"]:
            en_snippets.append(translator.translate_text_sync(snippet, "Chinese", "English"))

        mention = ProductMention(
            llm_answer_id=llm_answer.id,
            product_id=product.id,
            mentioned=True,
            rank=rank,
            sentiment=sentiment,
            evidence_snippets={"zh": mention_data["snippets"], "en": en_snippets},
        )
        db.add(mention)
    flush_with_retry(db)


def _products_to_variants(products: List[Product]) -> tuple[list[str], list[list[str]]]:
    names = []
    aliases = []
    for p in products:
        variants = _product_variants(p)
        names.append(variants[0] if variants else p.display_name)
        aliases.append(variants[1:] if len(variants) > 1 else [])
    return names, aliases


def _brands_to_variants(brands: List[Brand]) -> tuple[list[str], list[list[str]]]:
    names = []
    aliases = []
    for b in brands:
        names.append(b.display_name)
        aliases.append(_brand_aliases(b))
    return names, aliases


def _brand_aliases(brand: Brand) -> List[str]:
    variants = [brand.original_name or "", brand.translated_name or ""]
    variants.extend((brand.aliases or {}).get("zh", []))
    variants.extend((brand.aliases or {}).get("en", []))
    return [v for v in variants if v]


def _product_variants(product: Product) -> List[str]:
    variants = [product.display_name, product.original_name, product.translated_name or ""]
    seen: set[str] = set()
    result: List[str] = []
    for v in variants:
        if not v or v in seen:
            continue
        seen.add(v)
        result.append(v)
    return result


def _extract_product_snippet(text: str, product_name: str, max_len: int = 100) -> str:
    idx = text.lower().find(product_name.lower())
    if idx == -1:
        return ""
    start = max(0, idx - 30)
    end = min(len(text), idx + len(product_name) + 50)
    return text[start:end]


def _translate_snippets(snippets: List[str], translator) -> List[str]:
    en_snippets = []
    for snippet in snippets:
        en_snippet = translator.translate_text_sync(snippet, "Chinese", "English")
        en_snippets.append(en_snippet)
    return en_snippets
