import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import List

from celery import Task, chord, group
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import json

from config import settings
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
from models.domain import LLMRoute, RunStatus, Sentiment
from models.db_retry import commit_with_retry, flush_with_retry
from services.answer_reuse import find_reusable_answer
from services.brand_discovery import discover_brands_and_products
from services.brand_recognition import extract_entities
from services.entity_consolidation import consolidate_run
from services.brand_recognition.consolidation_service import run_enhanced_consolidation
from services.brand_recognition.product_brand_mapping import map_products_to_brands_for_run
from services.brand_recognition.vertical_gate import apply_vertical_gate_to_run
from services.product_discovery import discover_and_store_products
from services.translater import (
    TranslaterService,
    extract_chinese_part,
    extract_english_part,
    has_chinese_characters,
    has_latin_letters,
)
from services.metrics_service import calculate_and_save_metrics
from services.pricing import calculate_cost
from services.remote_llms import LLMRouter
from workers.celery_app import celery_app
from workers.llm_parallel import LLMRequest, LLMResult, fetch_llm_answers_parallel

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


@dataclass(frozen=True)
class _PromptWorkItem:
    prompt: Prompt
    prompt_text_zh: str
    prompt_text_en: str | None
    existing_answer: LLMAnswer | None
    reusable_answer: LLMAnswer | None


def _llm_fetch_concurrency(route: LLMRoute) -> int:
    if not settings.parallel_llm_enabled:
        return 1
    if route == LLMRoute.LOCAL:
        return max(1, settings.local_llm_concurrency)
    return max(1, settings.remote_llm_concurrency)


def _prompt_text_zh(prompt: Prompt, translator: TranslaterService) -> str | None:
    if prompt.text_zh:
        return prompt.text_zh
    if not prompt.text_en:
        return None
    logger.info(f"Translating English prompt to Chinese: {prompt.text_en[:50]}...")
    return translator.translate_text_sync(prompt.text_en, "English", "Chinese")


def _prompt_work_items(
    db: Session,
    run: Run,
    prompts: list[Prompt],
    translator: TranslaterService,
) -> tuple[list[_PromptWorkItem], list[LLMRequest]]:
    items: list[_PromptWorkItem] = []
    requests: list[LLMRequest] = []
    for prompt in prompts:
        prompt_text_zh = _prompt_text_zh(prompt, translator)
        if not prompt_text_zh:
            logger.warning(f"Prompt {prompt.id} has no text, skipping")
            continue
        existing = db.query(LLMAnswer).filter(LLMAnswer.run_id == run.id, LLMAnswer.prompt_id == prompt.id).first()
        reusable = None if existing else find_reusable_answer(db, run, prompt_text_zh=prompt_text_zh, prompt_text_en=prompt.text_en)
        items.append(_PromptWorkItem(prompt, prompt_text_zh, prompt.text_en, existing, reusable))
        if not existing and not reusable:
            requests.append(LLMRequest(prompt.id, prompt_text_zh))
    return items, requests


def _raise_on_llm_errors(results: list[LLMResult]) -> None:
    errors = [r.prompt_id for r in results if r.error]
    if errors:
        raise RuntimeError(f"LLM query failed for prompt_ids={errors}")


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


def _prompt_id_list(db: Session, run_id: int) -> list[int]:
    return [prompt_id for (prompt_id,) in db.query(Prompt.id).filter(Prompt.run_id == run_id).order_by(Prompt.id).all()]


def _existing_answer(db: Session, run_id: int, prompt_id: int) -> LLMAnswer | None:
    return db.query(LLMAnswer).filter(LLMAnswer.run_id == run_id, LLMAnswer.prompt_id == prompt_id).first()


def _ensure_prompt_text_zh(prompt: Prompt, translator: TranslaterService) -> str | None:
    if prompt.text_zh:
        return prompt.text_zh
    if not prompt.text_en:
        return None
    return translator.translate_text_sync(prompt.text_en, "English", "Chinese")


def _answer_payload(
    run_id: int,
    prompt_id: int,
    llm_answer_id: int | None,
    ok: bool,
    reused: bool,
    error: str | None = None,
) -> dict:
    return {
        "run_id": run_id,
        "prompt_id": prompt_id,
        "llm_answer_id": llm_answer_id,
        "ok": ok,
        "reused": reused,
        "stage": "answer",
        "error": error,
    }


def _extraction_payload(payload: dict, ok: bool, stage: str, error: str | None = None) -> dict:
    return {**payload, "ok": ok, "stage": stage, "error": error}


def _failed_prompt_ids(results: list[dict]) -> list[int]:
    return [int(r.get("prompt_id")) for r in results if not r.get("ok")]


def _should_fail_run(results: list[dict]) -> bool:
    total = max(1, len(results))
    failed = len(_failed_prompt_ids(results))
    if failed == 0:
        return False
    if failed > settings.fail_if_failed_prompts_gt:
        return True
    return failed / total > settings.fail_if_failed_rate_gt


def _llm_queue(route: LLMRoute) -> str:
    return "local_llm" if route == LLMRoute.LOCAL else "remote_llm"


@celery_app.task(base=DatabaseTask, bind=True)
def start_run(
    self: DatabaseTask,
    run_id: int,
    force_reextract: bool = False,
    skip_entity_consolidation: bool = False,
) -> dict:
    run = self.db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    llm_router = LLMRouter(self.db)
    resolution = llm_router.resolve(run.provider, run.model_name)
    run.route = resolution.route
    run.status = RunStatus.IN_PROGRESS
    run.error_message = None
    run.completed_at = None
    commit_with_retry(self.db)

    prompt_ids = _prompt_id_list(self.db, run_id)
    if not prompt_ids:
        run.status = RunStatus.FAILED
        run.error_message = f"No prompts found for run {run_id}"
        run.completed_at = datetime.utcnow()
        commit_with_retry(self.db)
        return {"run_id": run_id, "prompt_count": 0}

    header = []
    llm_queue = _llm_queue(resolution.route)
    for prompt_id in prompt_ids:
        header.append(
            ensure_llm_answer.s(run_id, prompt_id).set(queue=llm_queue)
            | ensure_extraction.s(run_id, force_reextract).set(queue="ollama_extract")
        )

    callback = finalize_run.s(run_id, force_reextract, skip_entity_consolidation).set(queue="default")
    chord(group(header))(callback)
    return {"run_id": run_id, "prompt_count": len(prompt_ids)}


@celery_app.task(base=DatabaseTask, bind=True)
def ensure_llm_answer(self: DatabaseTask, run_id: int, prompt_id: int) -> dict:
    try:
        run = self.db.query(Run).filter(Run.id == run_id).first()
        prompt = self.db.query(Prompt).filter(Prompt.id == prompt_id, Prompt.run_id == run_id).first()
        if not run or not prompt:
            return _answer_payload(run_id, prompt_id, None, False, False, "Run or prompt not found")

        existing = _existing_answer(self.db, run_id, prompt_id)
        if existing:
            return _answer_payload(run_id, prompt_id, existing.id, True, True)

        translator = TranslaterService()
        prompt_text_zh = _ensure_prompt_text_zh(prompt, translator)
        if not prompt_text_zh:
            return _answer_payload(run_id, prompt_id, None, False, False, "Prompt has no text")

        reusable = find_reusable_answer(self.db, run, prompt_text_zh=prompt_text_zh, prompt_text_en=prompt.text_en)
        if reusable:
            return _copy_reused_answer(self.db, run_id, prompt_id, run, reusable)

        llm_router = LLMRouter(self.db)
        resolution = llm_router.resolve(run.provider, run.model_name)
        answer_zh, tokens_in, tokens_out, latency = _run_async(
            llm_router.query_with_resolution(resolution, prompt_text_zh)
        )
        answer_en = translator.translate_text_sync(answer_zh, "Chinese", "English") if answer_zh else None
        cost_estimate = calculate_cost(run.provider, run.model_name, tokens_in, tokens_out, route=resolution.route)
        llm_answer = LLMAnswer(
            run_id=run_id,
            prompt_id=prompt_id,
            provider=run.provider,
            model_name=run.model_name,
            route=resolution.route,
            raw_answer_zh=answer_zh or "",
            raw_answer_en=answer_en,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency=latency,
            cost_estimate=cost_estimate,
        )
        self.db.add(llm_answer)
        flush_with_retry(self.db)
        commit_with_retry(self.db)
        return _answer_payload(run_id, prompt_id, llm_answer.id, True, False)
    except IntegrityError:
        self.db.rollback()
        existing = _existing_answer(self.db, run_id, prompt_id)
        if existing:
            return _answer_payload(run_id, prompt_id, existing.id, True, True)
        return _answer_payload(run_id, prompt_id, None, False, False, "IntegrityError on llm_answer insert")
    except Exception as exc:
        logger.error(f"ensure_llm_answer failed for run={run_id} prompt={prompt_id}: {exc}", exc_info=True)
        return _answer_payload(run_id, prompt_id, None, False, False, str(exc))


def _copy_reused_answer(db: Session, run_id: int, prompt_id: int, run: Run, reusable: LLMAnswer) -> dict:
    try:
        llm_answer = LLMAnswer(
            run_id=run_id,
            prompt_id=prompt_id,
            provider=run.provider,
            model_name=run.model_name,
            route=reusable.route,
            raw_answer_zh=reusable.raw_answer_zh,
            raw_answer_en=reusable.raw_answer_en,
            tokens_in=reusable.tokens_in,
            tokens_out=reusable.tokens_out,
            latency=reusable.latency,
            cost_estimate=reusable.cost_estimate,
        )
        db.add(llm_answer)
        flush_with_retry(db)
        commit_with_retry(db)
        return _answer_payload(run_id, prompt_id, llm_answer.id, True, True)
    except IntegrityError:
        db.rollback()
        existing = _existing_answer(db, run_id, prompt_id)
        if not existing:
            return _answer_payload(run_id, prompt_id, None, False, False, "IntegrityError on reused insert")
        return _answer_payload(run_id, prompt_id, existing.id, True, True)


@celery_app.task(base=DatabaseTask, bind=True)
def ensure_extraction(self: DatabaseTask, payload: dict, run_id: int, force_reextract: bool = False) -> dict:
    if not payload.get("ok") or not payload.get("llm_answer_id"):
        return _extraction_payload(payload, False, "extraction_skipped", payload.get("error"))

    prompt_id = int(payload["prompt_id"])
    llm_answer_id = int(payload["llm_answer_id"])
    try:
        answer = self.db.query(LLMAnswer).filter(LLMAnswer.id == llm_answer_id).first()
        run = self.db.query(Run).filter(Run.id == run_id).first()
        if not answer or not run:
            return _extraction_payload(payload, False, "extraction", "Run or answer not found")

        if not force_reextract and _has_mentions(self.db, llm_answer_id):
            return _extraction_payload(payload, True, "extraction_skipped", None)

        self.db.query(BrandMention).filter(BrandMention.llm_answer_id == llm_answer_id).delete()
        self.db.query(ProductMention).filter(ProductMention.llm_answer_id == llm_answer_id).delete()
        flush_with_retry(self.db)

        brands = self.db.query(Brand).filter(Brand.vertical_id == run.vertical_id).all()
        translator = TranslaterService()
        from services.ollama import OllamaService
        ollama_service = OllamaService()

        answer_zh = answer.raw_answer_zh or ""
        all_brands, extraction_result = discover_brands_and_products(answer_zh, run.vertical_id, brands, self.db)

        if extraction_result.debug_info:
            self.db.query(ExtractionDebug).filter(ExtractionDebug.llm_answer_id == llm_answer_id).delete()
            debug_record = ExtractionDebug(
                llm_answer_id=llm_answer_id,
                raw_brands=json.dumps(extraction_result.debug_info.raw_brands, ensure_ascii=False),
                raw_products=json.dumps(extraction_result.debug_info.raw_products, ensure_ascii=False),
                rejected_at_light_filter=json.dumps(extraction_result.debug_info.rejected_at_light_filter, ensure_ascii=False),
                final_brands=json.dumps(extraction_result.debug_info.final_brands, ensure_ascii=False),
                final_products=json.dumps(extraction_result.debug_info.final_products, ensure_ascii=False),
                extraction_method="qwen",
            )
            self.db.add(debug_record)

        discovered_products = discover_and_store_products(self.db, run.vertical_id, answer_zh, all_brands)

        brand_names = [b.display_name for b in all_brands]
        brand_aliases = [b.aliases.get("zh", []) + b.aliases.get("en", []) for b in all_brands]
        brand_mentions = _run_async(ollama_service.extract_brands(answer_zh, brand_names, brand_aliases))

        product_names, product_aliases = _products_to_variants(discovered_products)
        brand_names_for_products, brand_aliases_for_products = _brands_to_variants(all_brands)
        product_mentions = _run_async(
            ollama_service.extract_products(
                answer_zh, product_names, product_aliases, brand_names_for_products, brand_aliases_for_products
            )
        )

        all_snippets, snippet_map = _collect_all_snippets(brand_mentions, product_mentions)
        if settings.batch_translation_enabled and all_snippets:
            translated = translator.translate_batch_sync(all_snippets, "Chinese", "English")
        else:
            translated = [translator.translate_text_sync(s, "Chinese", "English") for s in all_snippets]

        for mention_data in brand_mentions:
            if not mention_data["mentioned"]:
                continue
            brand = all_brands[mention_data["brand_index"]]
            sentiment_str = "neutral"
            if mention_data["snippets"]:
                sentiment_str = _run_async(ollama_service.classify_sentiment(mention_data["snippets"][0]))
            sentiment = Sentiment.POSITIVE if sentiment_str == "positive" else (
                Sentiment.NEGATIVE if sentiment_str == "negative" else Sentiment.NEUTRAL
            )
            en_snippets = _get_translated_snippets("brand", mention_data["brand_index"], mention_data["snippets"], snippet_map, translated)
            self.db.add(BrandMention(
                llm_answer_id=llm_answer_id,
                brand_id=brand.id,
                mentioned=True,
                rank=mention_data["rank"],
                sentiment=sentiment,
                evidence_snippets={"zh": mention_data["snippets"], "en": en_snippets},
            ))

        for mention_data in product_mentions:
            if not mention_data["mentioned"] or mention_data["rank"] is None:
                continue
            product = discovered_products[mention_data["product_index"]]
            sentiment_str = "neutral"
            if mention_data["snippets"]:
                sentiment_str = _run_async(ollama_service.classify_sentiment(mention_data["snippets"][0]))
            sentiment = _map_sentiment(sentiment_str)
            en_snippets = _get_translated_snippets("product", mention_data["product_index"], mention_data["snippets"], snippet_map, translated)
            self.db.add(ProductMention(
                llm_answer_id=llm_answer_id,
                product_id=product.id,
                mentioned=True,
                rank=mention_data["rank"],
                sentiment=sentiment,
                evidence_snippets={"zh": mention_data["snippets"], "en": en_snippets},
            ))
        flush_with_retry(self.db)

        commit_with_retry(self.db)
        return _extraction_payload(payload, True, "extraction", None)
    except Exception as exc:
        logger.error(f"ensure_extraction failed for run={run_id} prompt={prompt_id}: {exc}", exc_info=True)
        return _extraction_payload(payload, False, "extraction", str(exc))


def _has_mentions(db: Session, llm_answer_id: int) -> bool:
    if db.query(BrandMention.id).filter(BrandMention.llm_answer_id == llm_answer_id).first():
        return True
    return db.query(ProductMention.id).filter(ProductMention.llm_answer_id == llm_answer_id).first() is not None


@celery_app.task(base=DatabaseTask, bind=True)
def finalize_run(
    self: DatabaseTask,
    results: list[dict],
    run_id: int,
    force_reextract: bool = False,
    skip_entity_consolidation: bool = False,
) -> dict:
    run = self.db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    failed_ids = _failed_prompt_ids(results)
    if _should_fail_run(results):
        run.status = RunStatus.FAILED
        run.error_message = f"Run failed: failed_prompts={len(failed_ids)} prompt_ids={failed_ids}"
        run.completed_at = datetime.utcnow()
        commit_with_retry(self.db)
        return {"run_id": run_id, "status": "failed", "failed_count": len(failed_ids), "failed_prompt_ids": failed_ids}

    _backfill_entity_english_names(self.db, run)

    enhanced_result = _run_async(run_enhanced_consolidation(self.db, run_id))
    _run_async(apply_vertical_gate_to_run(self.db, run_id))
    if not skip_entity_consolidation:
        consolidate_run(self.db, run_id, normalized_brands=enhanced_result.normalized_brands)
    _run_async(map_products_to_brands_for_run(self.db, run_id))
    calculate_and_save_metrics(self.db, run_id)

    run.status = RunStatus.COMPLETED
    run.completed_at = datetime.utcnow()
    if failed_ids:
        run.error_message = f"Completed with warnings: failed_prompts={len(failed_ids)} prompt_ids={failed_ids}"
    commit_with_retry(self.db)
    return {"run_id": run_id, "status": "completed", "failed_count": len(failed_ids), "failed_prompt_ids": failed_ids}


def _mentioned_brand_ids(db: Session, run_id: int) -> list[int]:
    rows = (
        db.query(BrandMention.brand_id)
        .join(LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id, BrandMention.mentioned)
        .distinct()
        .all()
    )
    return [int(r[0]) for r in rows]


def _mentioned_product_ids(db: Session, run_id: int) -> list[int]:
    rows = (
        db.query(ProductMention.product_id)
        .join(LLMAnswer, LLMAnswer.id == ProductMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id, ProductMention.mentioned)
        .distinct()
        .all()
    )
    return [int(r[0]) for r in rows]


def _normalize_mixed_original_name(name: str) -> tuple[str, str]:
    english = extract_english_part(name)
    chinese = extract_chinese_part(name)
    return english.strip(), chinese.strip()


def _append_alias(aliases: dict, lang: str, value: str) -> dict:
    aliases = aliases or {"zh": [], "en": []}
    aliases.setdefault("zh", [])
    aliases.setdefault("en", [])
    if value and value not in aliases[lang]:
        aliases[lang].append(value)
    return aliases


def _backfill_entity_english_names(db: Session, run: Run) -> None:
    vertical = db.query(Vertical).filter(Vertical.id == run.vertical_id).first()
    if not vertical:
        return
    brands = db.query(Brand).filter(Brand.id.in_(_mentioned_brand_ids(db, run.id))).all()
    products = db.query(Product).filter(Product.id.in_(_mentioned_product_ids(db, run.id))).all()
    translator = TranslaterService()
    _normalize_run_entities(brands, products)
    items = _entities_missing_english(brands, products)
    if items:
        mapping = _run_async(translator.translate_entities_to_english_batch(items, vertical.name, vertical.description))
        _apply_entity_english_mapping(brands, products, mapping)
    commit_with_retry(db)


def _normalize_run_entities(brands: list[Brand], products: list[Product]) -> None:
    for brand in brands:
        if has_latin_letters(brand.original_name) and has_chinese_characters(brand.original_name):
            english, chinese = _normalize_mixed_original_name(brand.original_name)
            if english:
                brand.original_name = english
                brand.translated_name = None
            if chinese:
                brand.aliases = _append_alias(brand.aliases, "zh", chinese)
            if english:
                brand.aliases = _append_alias(brand.aliases, "en", english)
    for product in products:
        if has_latin_letters(product.original_name) and has_chinese_characters(product.original_name):
            english, _ = _normalize_mixed_original_name(product.original_name)
            if english:
                product.original_name = english
                product.translated_name = None


def _entities_missing_english(brands: list[Brand], products: list[Product]) -> list[dict]:
    items: list[dict] = []
    for brand in brands:
        if brand.translated_name:
            continue
        if has_chinese_characters(brand.original_name) and not has_latin_letters(brand.original_name):
            items.append({"type": "brand", "name": brand.original_name.strip()})
    for product in products:
        if product.translated_name:
            continue
        if has_chinese_characters(product.original_name) and not has_latin_letters(product.original_name):
            items.append({"type": "product", "name": product.original_name.strip()})
    return items


def _apply_entity_english_mapping(
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
        brand.aliases = _append_alias(brand.aliases, "en", english)
    for product in products:
        key = ("product", (product.original_name or "").strip())
        english = mapping.get(key)
        if not english:
            continue
        product.translated_name = english


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

        work_items, llm_requests = _prompt_work_items(self.db, run, prompts, translator)
        concurrency = _llm_fetch_concurrency(resolution.route)
        logger.info(f"LLM parallel fetch: enabled={settings.parallel_llm_enabled}, concurrency={concurrency}, prompts={len(llm_requests)}")

        async def _query_fn(prompt_zh: str):
            return await llm_router.query_with_resolution(resolution, prompt_zh)

        llm_results_by_prompt_id: dict[int, LLMResult] = {}
        if llm_requests:
            if concurrency > 1 and len(llm_requests) > 1:
                llm_results = _run_async(fetch_llm_answers_parallel(llm_requests, _query_fn, concurrency))
                _raise_on_llm_errors(llm_results)
                llm_results_by_prompt_id = {r.prompt_id: r for r in llm_results}
            else:
                for req in llm_requests:
                    answer_zh, tokens_in, tokens_out, latency = _run_async(_query_fn(req.prompt_text_zh))
                    llm_results_by_prompt_id[req.prompt_id] = LLMResult(
                        prompt_id=req.prompt_id,
                        answer_zh=answer_zh,
                        tokens_in=tokens_in,
                        tokens_out=tokens_out,
                        latency=latency,
                    )

        for item in work_items:
            prompt = item.prompt
            logger.info(f"Processing prompt {prompt.id}")

            llm_answer = None
            answer_zh = ""
            answer_en = None
            tokens_in = 0
            tokens_out = 0
            latency = 0.0
            cost_estimate = 0.0

            if item.existing_answer:
                llm_answer = item.existing_answer
                answer_zh = llm_answer.raw_answer_zh
                self.db.query(BrandMention).filter(BrandMention.llm_answer_id == llm_answer.id).delete()
                self.db.query(ProductMention).filter(ProductMention.llm_answer_id == llm_answer.id).delete()
                flush_with_retry(self.db)
            elif item.reusable_answer:
                reusable = item.reusable_answer
                answer_zh = reusable.raw_answer_zh
                answer_en = reusable.raw_answer_en
                tokens_in = reusable.tokens_in or 0
                tokens_out = reusable.tokens_out or 0
                latency = reusable.latency or 0.0
                cost_estimate = reusable.cost_estimate or 0.0
            else:
                result = llm_results_by_prompt_id.get(prompt.id)
                if not result:
                    raise RuntimeError(f"Missing LLM result for prompt {prompt.id}")
                answer_zh = result.answer_zh
                tokens_in = result.tokens_in
                tokens_out = result.tokens_out
                latency = result.latency
                cost_estimate = calculate_cost(provider, model_name, tokens_in, tokens_out, route=resolution.route)

            if not llm_answer:
                answer_route = resolution.route
                if item.reusable_answer and item.reusable_answer.route:
                    answer_route = item.reusable_answer.route
                if answer_zh and not answer_en and not item.reusable_answer:
                    answer_en = translator.translate_text_sync(answer_zh, "Chinese", "English")
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
                self.db.query(ExtractionDebug).filter(ExtractionDebug.llm_answer_id == llm_answer.id).delete()
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

            brand_names = [b.display_name for b in all_brands]
            brand_aliases = [b.aliases.get("zh", []) + b.aliases.get("en", []) for b in all_brands]

            logger.info(f"Extracting brand mentions for {len(all_brands)} brands...")
            brand_mentions_data = _run_async(
                ollama_service.extract_brands(answer_zh, brand_names, brand_aliases)
            )

            product_names, product_aliases = _products_to_variants(discovered_products)
            brand_names_for_products, brand_aliases_for_products = _brands_to_variants(all_brands)
            product_mentions_data = _run_async(
                ollama_service.extract_products(
                    answer_zh, product_names, product_aliases, brand_names_for_products, brand_aliases_for_products
                )
            )

            all_snippets, snippet_map = _collect_all_snippets(brand_mentions_data, product_mentions_data)
            if settings.batch_translation_enabled and all_snippets:
                logger.info(f"Batch translating {len(all_snippets)} snippets...")
                translated = translator.translate_batch_sync(all_snippets, "Chinese", "English")
            else:
                translated = [translator.translate_text_sync(s, "Chinese", "English") for s in all_snippets]

            for mention_data in brand_mentions_data:
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
                en_snippets = _get_translated_snippets("brand", mention_data["brand_index"], mention_data["snippets"], snippet_map, translated)
                mention = BrandMention(
                    llm_answer_id=llm_answer.id,
                    brand_id=brand.id,
                    mentioned=True,
                    rank=mention_data["rank"],
                    sentiment=sentiment,
                    evidence_snippets={"zh": mention_data["snippets"], "en": en_snippets},
                )
                self.db.add(mention)

            for mention_data in product_mentions_data:
                if not mention_data["mentioned"] or mention_data["rank"] is None:
                    continue
                product = discovered_products[mention_data["product_index"]]
                sentiment_str = "neutral"
                if mention_data["snippets"]:
                    sentiment_str = _run_async(ollama_service.classify_sentiment(mention_data["snippets"][0]))
                sentiment = _map_sentiment(sentiment_str)
                en_snippets = _get_translated_snippets("product", mention_data["product_index"], mention_data["snippets"], snippet_map, translated)
                self.db.add(ProductMention(
                    llm_answer_id=llm_answer.id,
                    product_id=product.id,
                    mentioned=True,
                    rank=mention_data["rank"],
                    sentiment=sentiment,
                    evidence_snippets={"zh": mention_data["snippets"], "en": en_snippets},
                ))
            flush_with_retry(self.db)

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

        logger.info(f"Mapping products to brands for run {run_id}...")
        mapped = _run_async(map_products_to_brands_for_run(self.db, run_id))
        logger.info(f"Product brand mapping complete: {len(mapped)} products mapped")

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


def _collect_all_snippets(
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


def _get_translated_snippets(
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
