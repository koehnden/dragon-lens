"""Parallel processing pipeline for LLM queries and entity extraction."""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models import Brand, BrandMention, ExtractionDebug, LLMAnswer, Product, ProductMention, Prompt, Run
from models.db_retry import commit_with_retry, flush_with_retry
from models.domain import LLMRoute, Sentiment
from services.pricing import calculate_cost

logger = logging.getLogger(__name__)

REMOTE_LLM_SEMAPHORE: Optional[asyncio.Semaphore] = None
OLLAMA_SEMAPHORE: Optional[asyncio.Semaphore] = None


def _get_remote_semaphore() -> asyncio.Semaphore:
    global REMOTE_LLM_SEMAPHORE
    if REMOTE_LLM_SEMAPHORE is None:
        REMOTE_LLM_SEMAPHORE = asyncio.Semaphore(3)
    return REMOTE_LLM_SEMAPHORE


def _get_ollama_semaphore() -> asyncio.Semaphore:
    global OLLAMA_SEMAPHORE
    if OLLAMA_SEMAPHORE is None:
        OLLAMA_SEMAPHORE = asyncio.Semaphore(5)
    return OLLAMA_SEMAPHORE


@dataclass
class PromptContext:
    prompt: Prompt
    prompt_text_zh: str
    prompt_text_en: Optional[str]


@dataclass
class LLMQueryResult:
    context: PromptContext
    answer_zh: str
    answer_en: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency: float = 0.0
    cost_estimate: float = 0.0
    is_reused: bool = False
    reused_route: Optional[LLMRoute] = None
    existing_answer: Optional[LLMAnswer] = None
    error: Optional[str] = None


@dataclass
class MentionData:
    brand: Brand
    rank: int
    sentiment: Sentiment
    zh_snippets: list[str]
    en_snippets: list[str]


@dataclass
class ProductMentionData:
    product: Product
    rank: int
    sentiment: Sentiment
    zh_snippets: list[str]
    en_snippets: list[str]


@dataclass
class FeatureMentionData:
    feature_name_zh: str
    feature_name_en: Optional[str]
    sentiment: Sentiment
    snippet_zh: str
    snippet_en: Optional[str]
    entity_type: str
    entity_id: int


@dataclass
class ExtractionResult:
    query_result: LLMQueryResult
    llm_answer: Optional[LLMAnswer] = None
    discovered_brands: list[Brand] = field(default_factory=list)
    discovered_products: list[Product] = field(default_factory=list)
    brand_mentions: list[MentionData] = field(default_factory=list)
    product_mentions: list[ProductMentionData] = field(default_factory=list)
    feature_mentions: list[FeatureMentionData] = field(default_factory=list)
    debug_info: Optional[dict] = None
    error: Optional[str] = None


def prepare_prompts(prompts: list[Prompt], translator) -> list[PromptContext]:
    contexts = []
    for prompt in prompts:
        prompt_text_zh = prompt.text_zh
        prompt_text_en = prompt.text_en
        if not prompt_text_zh and prompt_text_en:
            logger.info(f"Translating English prompt {prompt.id} to Chinese...")
            prompt_text_zh = translator.translate_text_sync(prompt_text_en, "English", "Chinese")
        if not prompt_text_zh:
            logger.warning(f"Prompt {prompt.id} has no text, skipping")
            continue
        contexts.append(PromptContext(prompt, prompt_text_zh, prompt_text_en))
    return contexts


async def _fetch_single_llm_answer(
    context: PromptContext,
    resolution,
    llm_router,
    db: Session,
    run: Run,
    provider: str,
    model_name: str,
) -> LLMQueryResult:
    from services.answer_reuse import find_reusable_answer

    prompt = context.prompt
    existing = db.query(LLMAnswer).filter(
        LLMAnswer.run_id == run.id,
        LLMAnswer.prompt_id == prompt.id
    ).first()

    if existing:
        logger.info(f"Found existing answer for prompt {prompt.id}")
        return LLMQueryResult(
            context=context,
            answer_zh=existing.raw_answer_zh,
            answer_en=existing.raw_answer_en,
            tokens_in=existing.tokens_in,
            tokens_out=existing.tokens_out,
            latency=existing.latency or 0.0,
            cost_estimate=existing.cost_estimate or 0.0,
            is_reused=True,
            existing_answer=existing,
        )

    reusable = find_reusable_answer(
        db, run,
        prompt_text_zh=context.prompt_text_zh,
        prompt_text_en=context.prompt_text_en,
    )

    if reusable:
        logger.info(f"Reusing answer from previous run for prompt {prompt.id}")
        return LLMQueryResult(
            context=context,
            answer_zh=reusable.raw_answer_zh,
            answer_en=reusable.raw_answer_en,
            tokens_in=reusable.tokens_in,
            tokens_out=reusable.tokens_out,
            latency=reusable.latency or 0.0,
            cost_estimate=reusable.cost_estimate or 0.0,
            is_reused=True,
            reused_route=reusable.route,
        )

    try:
        async with _get_remote_semaphore():
            logger.info(f"Querying {provider}/{model_name} for prompt {prompt.id}...")
            answer_zh, tokens_in, tokens_out, latency = await llm_router.query_with_resolution(
                resolution, context.prompt_text_zh
            )
            logger.info(f"Received answer for prompt {prompt.id}: {answer_zh[:80]}...")

        cost = calculate_cost(provider, model_name, tokens_in, tokens_out, route=resolution.route)
        return LLMQueryResult(
            context=context,
            answer_zh=answer_zh,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency=latency,
            cost_estimate=cost,
            is_reused=False,
        )
    except Exception as e:
        logger.error(f"Error querying LLM for prompt {prompt.id}: {e}")
        return LLMQueryResult(context=context, answer_zh="", error=str(e))


async def fetch_all_llm_answers(
    contexts: list[PromptContext],
    resolution,
    llm_router,
    db: Session,
    run: Run,
    provider: str,
    model_name: str,
) -> list[LLMQueryResult]:
    logger.info(f"Fetching {len(contexts)} LLM answers in parallel...")

    tasks = [
        _fetch_single_llm_answer(ctx, resolution, llm_router, db, run, provider, model_name)
        for ctx in contexts
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    processed = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Exception for prompt {contexts[i].prompt.id}: {result}")
            processed.append(LLMQueryResult(context=contexts[i], answer_zh="", error=str(result)))
        else:
            processed.append(result)

    success_count = sum(1 for r in processed if not r.error and r.answer_zh)
    logger.info(f"Fetched {success_count}/{len(contexts)} answers successfully")
    return processed


async def _translate_single_answer(result: LLMQueryResult, translator) -> LLMQueryResult:
    if result.error or not result.answer_zh or result.answer_en:
        return result

    try:
        async with _get_ollama_semaphore():
            loop = asyncio.get_event_loop()
            answer_en = await loop.run_in_executor(
                None,
                translator.translate_text_sync,
                result.answer_zh,
                "Chinese",
                "English"
            )
            result.answer_en = answer_en
    except Exception as e:
        logger.error(f"Error translating answer for prompt {result.context.prompt.id}: {e}")
    return result


async def translate_all_answers(results: list[LLMQueryResult], translator) -> list[LLMQueryResult]:
    to_translate = [r for r in results if not r.error and r.answer_zh and not r.answer_en]
    logger.info(f"Translating {len(to_translate)} answers in parallel...")

    tasks = [_translate_single_answer(r, translator) for r in to_translate]
    await asyncio.gather(*tasks)

    return results


async def _extract_single_result(
    result: LLMQueryResult,
    vertical_id: int,
    user_brands: list[Brand],
    db: Session,
    ollama_service,
    translator,
    run_id: int,
    provider: str,
    model_name: str,
    resolution,
) -> ExtractionResult:
    import json
    from services.brand_discovery import discover_brands_and_products
    from services.product_discovery import discover_and_store_products

    if result.error or not result.answer_zh:
        return ExtractionResult(query_result=result, error=result.error or "No answer")

    try:
        answer_zh = result.answer_zh
        prompt = result.context.prompt

        if result.existing_answer:
            llm_answer = result.existing_answer
            db.query(BrandMention).filter(BrandMention.llm_answer_id == llm_answer.id).delete()
            db.query(ProductMention).filter(ProductMention.llm_answer_id == llm_answer.id).delete()
        else:
            answer_route = resolution.route
            if result.reused_route:
                answer_route = result.reused_route
            llm_answer = LLMAnswer(
                run_id=run_id,
                prompt_id=prompt.id,
                provider=provider,
                model_name=model_name,
                route=answer_route,
                raw_answer_zh=result.answer_zh,
                raw_answer_en=result.answer_en,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                latency=result.latency,
                cost_estimate=result.cost_estimate,
            )
            db.add(llm_answer)
            flush_with_retry(db)

        all_brands, extraction_result = discover_brands_and_products(
            answer_zh, vertical_id, user_brands, db
        )

        debug_info = None
        if extraction_result.debug_info:
            debug_info = {
                "raw_brands": extraction_result.debug_info.raw_brands,
                "raw_products": extraction_result.debug_info.raw_products,
                "rejected_at_light_filter": extraction_result.debug_info.rejected_at_light_filter,
                "final_brands": extraction_result.debug_info.final_brands,
                "final_products": extraction_result.debug_info.final_products,
            }

        discovered_products = discover_and_store_products(
            db,
            vertical_id,
            answer_zh,
            all_brands,
            extraction_relationships=extraction_result.product_brand_relationships,
        )

        product_mentions = await _extract_product_mentions(
            llm_answer, discovered_products, answer_zh, translator, all_brands, ollama_service
        )

        brand_mentions = await _extract_brand_mentions(
            answer_zh, all_brands, ollama_service, translator
        )

        return ExtractionResult(
            query_result=result,
            llm_answer=llm_answer,
            discovered_brands=all_brands,
            discovered_products=discovered_products,
            brand_mentions=brand_mentions,
            product_mentions=product_mentions,
            debug_info=debug_info,
        )
    except Exception as e:
        logger.error(f"Error extracting entities for prompt {result.context.prompt.id}: {e}", exc_info=True)
        return ExtractionResult(query_result=result, error=str(e))


async def _extract_product_mentions(
    llm_answer: LLMAnswer,
    products: list[Product],
    answer_zh: str,
    translator,
    brands: list[Brand],
    ollama_service,
) -> list[ProductMentionData]:
    if not products:
        return []

    product_names = [p.display_name for p in products]
    product_aliases = [_product_aliases(p) for p in products]
    brand_names = [b.display_name for b in brands]
    brand_aliases = [_brand_aliases(b) for b in brands]

    async with _get_ollama_semaphore():
        mentions = await ollama_service.extract_products(
            answer_zh, product_names, product_aliases, brand_names, brand_aliases
        )

    results = []
    for mention_data in mentions:
        if not mention_data["mentioned"] or mention_data["rank"] is None:
            continue
        product = products[mention_data["product_index"]]

        sentiment_str = "neutral"
        if mention_data["snippets"]:
            async with _get_ollama_semaphore():
                sentiment_str = await ollama_service.classify_sentiment(mention_data["snippets"][0])

        sentiment = _map_sentiment(sentiment_str)
        en_snippets = _translate_snippets_sync(mention_data["snippets"], translator)

        results.append(ProductMentionData(
            product=product,
            rank=mention_data["rank"],
            sentiment=sentiment,
            zh_snippets=mention_data["snippets"],
            en_snippets=en_snippets,
        ))
    return results


async def _extract_brand_mentions(
    answer_zh: str,
    all_brands: list[Brand],
    ollama_service,
    translator,
) -> list[MentionData]:
    if not all_brands:
        return []

    brand_names = [b.display_name for b in all_brands]
    brand_aliases = [_brand_aliases(b) for b in all_brands]

    async with _get_ollama_semaphore():
        mentions = await ollama_service.extract_brands(answer_zh, brand_names, brand_aliases)

    results = []
    for mention_data in mentions:
        if not mention_data["mentioned"]:
            continue
        brand = all_brands[mention_data["brand_index"]]

        sentiment_str = "neutral"
        if mention_data["snippets"]:
            async with _get_ollama_semaphore():
                sentiment_str = await ollama_service.classify_sentiment(mention_data["snippets"][0])

        sentiment = _map_sentiment(sentiment_str)
        en_snippets = _translate_snippets_sync(mention_data["snippets"], translator)

        results.append(MentionData(
            brand=brand,
            rank=mention_data["rank"],
            sentiment=sentiment,
            zh_snippets=mention_data["snippets"],
            en_snippets=en_snippets,
        ))
    return results


def _brand_aliases(brand: Brand) -> list[str]:
    variants = [brand.original_name or "", brand.translated_name or ""]
    variants.extend((brand.aliases or {}).get("zh", []))
    variants.extend((brand.aliases or {}).get("en", []))
    return [v for v in variants if v]


def _product_aliases(product: Product) -> list[str]:
    variants = [product.original_name or "", product.translated_name or ""]
    return [v for v in variants if v]


def _map_sentiment(sentiment_str: str) -> Sentiment:
    if sentiment_str == "positive":
        return Sentiment.POSITIVE
    if sentiment_str == "negative":
        return Sentiment.NEGATIVE
    return Sentiment.NEUTRAL


def _translate_snippets_sync(snippets: list[str], translator) -> list[str]:
    return [translator.translate_text_sync(s, "Chinese", "English") for s in snippets]


async def extract_all_entities(
    results: list[LLMQueryResult],
    vertical_id: int,
    user_brands: list[Brand],
    db: Session,
    ollama_service,
    translator,
    run_id: int,
    provider: str,
    model_name: str,
    resolution,
) -> list[ExtractionResult]:
    valid_results = [r for r in results if not r.error and r.answer_zh]
    logger.info(f"Extracting entities from {len(valid_results)} answers...")

    extraction_results = []
    for result in valid_results:
        ext_result = await _extract_single_result(
            result, vertical_id, user_brands, db, ollama_service, translator,
            run_id, provider, model_name, resolution
        )
        extraction_results.append(ext_result)

    success_count = sum(1 for r in extraction_results if not r.error)
    logger.info(f"Extracted entities from {success_count}/{len(valid_results)} answers")
    return extraction_results


def batch_save_mentions(db: Session, extraction_results: list[ExtractionResult]) -> None:
    import json

    for ext in extraction_results:
        if ext.error or not ext.llm_answer:
            continue

        if ext.debug_info:
            debug_record = ExtractionDebug(
                llm_answer_id=ext.llm_answer.id,
                raw_brands=json.dumps(ext.debug_info.get("raw_brands", []), ensure_ascii=False),
                raw_products=json.dumps(ext.debug_info.get("raw_products", []), ensure_ascii=False),
                rejected_at_light_filter=json.dumps(ext.debug_info.get("rejected_at_light_filter", []), ensure_ascii=False),
                final_brands=json.dumps(ext.debug_info.get("final_brands", []), ensure_ascii=False),
                final_products=json.dumps(ext.debug_info.get("final_products", []), ensure_ascii=False),
                extraction_method="qwen",
            )
            db.add(debug_record)

        for mention in ext.brand_mentions:
            db_mention = BrandMention(
                llm_answer_id=ext.llm_answer.id,
                brand_id=mention.brand.id,
                mentioned=True,
                rank=mention.rank,
                sentiment=mention.sentiment,
                evidence_snippets={"zh": mention.zh_snippets, "en": mention.en_snippets},
            )
            db.add(db_mention)

        for mention in ext.product_mentions:
            db_mention = ProductMention(
                llm_answer_id=ext.llm_answer.id,
                product_id=mention.product.id,
                mentioned=True,
                rank=mention.rank,
                sentiment=mention.sentiment,
                evidence_snippets={"zh": mention.zh_snippets, "en": mention.en_snippets},
            )
            db.add(db_mention)

    commit_with_retry(db)
    logger.info(f"Saved mentions for {len(extraction_results)} answers")


async def extract_features_from_mentions(
    extraction_results: list[ExtractionResult],
    ollama_service,
    translator,
) -> list[FeatureMentionData]:
    from services.feature_extraction import extract_features_from_snippet

    all_features: list[FeatureMentionData] = []

    for ext in extraction_results:
        if ext.error:
            continue

        for mention in ext.brand_mentions:
            features = await _extract_features_for_entity(
                mention.zh_snippets,
                mention.en_snippets,
                "brand",
                mention.brand.id,
                mention.brand.display_name,
                ollama_service,
                translator,
            )
            all_features.extend(features)

        for mention in ext.product_mentions:
            features = await _extract_features_for_entity(
                mention.zh_snippets,
                mention.en_snippets,
                "product",
                mention.product.id,
                mention.product.display_name,
                ollama_service,
                translator,
            )
            all_features.extend(features)

    logger.info(f"Extracted {len(all_features)} feature mentions")
    return all_features


async def _extract_features_for_entity(
    zh_snippets: list[str],
    en_snippets: list[str],
    entity_type: str,
    entity_id: int,
    entity_name: str,
    ollama_service,
    translator,
) -> list[FeatureMentionData]:
    from services.feature_extraction import extract_features_from_snippet

    features: list[FeatureMentionData] = []

    for i, snippet_zh in enumerate(zh_snippets):
        if not snippet_zh or not snippet_zh.strip():
            continue

        snippet_en = en_snippets[i] if i < len(en_snippets) else None

        try:
            async with _get_ollama_semaphore():
                extracted = await extract_features_from_snippet(
                    snippet_zh,
                    ollama_service,
                    brand_name=entity_name if entity_type == "brand" else None,
                    product_name=entity_name if entity_type == "product" else None,
                )

            for feat in extracted:
                sentiment = _map_sentiment(feat.get("sentiment", "neutral"))
                features.append(FeatureMentionData(
                    feature_name_zh=feat["feature_zh"],
                    feature_name_en=feat.get("feature_en"),
                    sentiment=sentiment,
                    snippet_zh=snippet_zh,
                    snippet_en=snippet_en,
                    entity_type=entity_type,
                    entity_id=entity_id,
                ))
        except Exception as e:
            logger.warning(f"Error extracting features for {entity_type} {entity_id}: {e}")

    return features


def batch_save_feature_mentions(
    db: Session,
    run_id: int,
    vertical_id: int,
    feature_mentions: list[FeatureMentionData],
    brand_mentions_by_entity: dict,
    product_mentions_by_entity: dict,
) -> None:
    from models import EntityType, Feature, FeatureMention, RunFeatureMetrics
    from services.feature_consolidation import consolidate_feature_list
    from services.feature_metrics_service import calculate_combined_score

    if not feature_mentions:
        logger.info("No feature mentions to save")
        return

    feature_names = list({f.feature_name_zh for f in feature_mentions})
    canonical_map = consolidate_feature_list(feature_names)

    feature_cache: dict[str, Feature] = {}

    for fm in feature_mentions:
        canonical_name = canonical_map.get(fm.feature_name_zh, fm.feature_name_zh)
        feature = _get_or_create_feature(db, vertical_id, canonical_name, fm.feature_name_en, feature_cache)

        brand_mention_id = None
        product_mention_id = None

        if fm.entity_type == "brand":
            brand_mention_id = brand_mentions_by_entity.get(fm.entity_id)
        else:
            product_mention_id = product_mentions_by_entity.get(fm.entity_id)

        db_fm = FeatureMention(
            feature_id=feature.id,
            brand_mention_id=brand_mention_id,
            product_mention_id=product_mention_id,
            snippet_zh=fm.snippet_zh,
            snippet_en=fm.snippet_en,
            sentiment=fm.sentiment,
        )
        db.add(db_fm)

    flush_with_retry(db)

    _calculate_and_save_feature_metrics(db, run_id, vertical_id, feature_mentions, canonical_map, feature_cache)

    commit_with_retry(db)
    logger.info(f"Saved {len(feature_mentions)} feature mentions")


def _get_or_create_feature(
    db: Session,
    vertical_id: int,
    canonical_name: str,
    feature_name_en: Optional[str],
    cache: dict,
) -> "Feature":
    from models import Feature

    cache_key = f"{vertical_id}:{canonical_name}"
    if cache_key in cache:
        return cache[cache_key]

    feature = db.query(Feature).filter(
        Feature.vertical_id == vertical_id,
        Feature.canonical_name == canonical_name,
    ).first()

    if not feature:
        feature = Feature(
            vertical_id=vertical_id,
            canonical_name=canonical_name,
            display_name_zh=canonical_name,
            display_name_en=feature_name_en,
            mention_count=0,
        )
        db.add(feature)
        flush_with_retry(db)

    feature.mention_count += 1
    cache[cache_key] = feature
    return feature


def _calculate_and_save_feature_metrics(
    db: Session,
    run_id: int,
    vertical_id: int,
    feature_mentions: list[FeatureMentionData],
    canonical_map: dict[str, str],
    feature_cache: dict,
) -> None:
    from collections import defaultdict
    from models import EntityType, RunFeatureMetrics
    from services.feature_metrics_service import calculate_combined_score

    entity_features: dict[tuple[str, int], dict[str, dict]] = defaultdict(lambda: defaultdict(lambda: {
        "frequency": 0, "positive": 0, "neutral": 0, "negative": 0
    }))

    for fm in feature_mentions:
        canonical_name = canonical_map.get(fm.feature_name_zh, fm.feature_name_zh)
        key = (fm.entity_type, fm.entity_id)
        stats = entity_features[key][canonical_name]
        stats["frequency"] += 1

        if fm.sentiment == Sentiment.POSITIVE:
            stats["positive"] += 1
        elif fm.sentiment == Sentiment.NEGATIVE:
            stats["negative"] += 1
        else:
            stats["neutral"] += 1

    for (entity_type, entity_id), features in entity_features.items():
        for feature_name, stats in features.items():
            cache_key = f"{vertical_id}:{feature_name}"
            feature = feature_cache.get(cache_key)
            if not feature:
                continue

            combined_score = calculate_combined_score(
                stats["frequency"],
                stats["positive"],
                stats["neutral"],
                stats["negative"],
            )

            metric = RunFeatureMetrics(
                run_id=run_id,
                entity_type=EntityType.BRAND if entity_type == "brand" else EntityType.PRODUCT,
                entity_id=entity_id,
                feature_id=feature.id,
                frequency=stats["frequency"],
                positive_count=stats["positive"],
                neutral_count=stats["neutral"],
                negative_count=stats["negative"],
                combined_score=combined_score,
            )
            db.add(metric)


async def run_parallel_pipeline(
    db: Session,
    run: Run,
    prompts: list[Prompt],
    brands: list[Brand],
    resolution,
    llm_router,
    translator,
    ollama_service,
    provider: str,
    model_name: str,
) -> list[ExtractionResult]:
    logger.info(f"Starting parallel pipeline for {len(prompts)} prompts...")

    contexts = prepare_prompts(prompts, translator)
    if not contexts:
        logger.warning("No valid prompts to process")
        return []

    llm_results = await fetch_all_llm_answers(
        contexts, resolution, llm_router, db, run, provider, model_name
    )

    llm_results = await translate_all_answers(llm_results, translator)

    extraction_results = await extract_all_entities(
        llm_results, run.vertical_id, brands, db, ollama_service, translator,
        run.id, provider, model_name, resolution
    )

    batch_save_mentions(db, extraction_results)

    feature_mentions = await extract_features_from_mentions(
        extraction_results, ollama_service, translator
    )

    mention_maps = _build_mention_id_maps(db, extraction_results)
    batch_save_feature_mentions(
        db, run.id, run.vertical_id, feature_mentions,
        mention_maps["brand"], mention_maps["product"]
    )

    logger.info(f"Parallel pipeline complete for {len(prompts)} prompts")
    return extraction_results


def _build_mention_id_maps(
    db: Session,
    extraction_results: list[ExtractionResult],
) -> dict[str, dict[int, int]]:
    brand_map: dict[int, int] = {}
    product_map: dict[int, int] = {}

    for ext in extraction_results:
        if ext.error or not ext.llm_answer:
            continue

        for mention in db.query(BrandMention).filter(
            BrandMention.llm_answer_id == ext.llm_answer.id
        ).all():
            brand_map[mention.brand_id] = mention.id

        for mention in db.query(ProductMention).filter(
            ProductMention.llm_answer_id == ext.llm_answer.id
        ).all():
            product_map[mention.product_id] = mention.id

    return {"brand": brand_map, "product": product_map}
