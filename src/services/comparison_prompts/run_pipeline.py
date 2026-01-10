from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import (
    Brand,
    ComparisonAnswer,
    ComparisonEntityRole,
    ComparisonPrompt,
    ComparisonPromptSource,
    ComparisonPromptType,
    ComparisonRunEvent,
    ComparisonRunStatus,
    ComparisonSentimentObservation,
    EntityType,
    LLMAnswer,
    Product,
    ProductMention,
    Run,
    RunComparisonConfig,
    RunMetrics,
    RunProductMetrics,
    Sentiment,
)
from services.comparison_prompts.generation import build_comparison_prompt_generation_prompt
from services.comparison_prompts.parser import parse_comparison_prompts_from_text
from services.comparison_prompts.planner import competitor_missing_counts, total_generation_count
from services.remote_llms import LLMRouter
from services.translater import TranslaterService
from services.ollama import OllamaService

logger = logging.getLogger(__name__)


async def run_comparison_pipeline(db: Session, run_id: int, k_products: int = 5, top_competitors: int = 5) -> None:
    run = _run_or_none(db, run_id)
    config = _config_or_none(db, run_id)
    if not run or not config or not config.enabled:
        return
    if config.status == ComparisonRunStatus.COMPLETED:
        return
    _set_status(db, config, ComparisonRunStatus.IN_PROGRESS, None)
    await _run_pipeline(db, run, config, k_products, top_competitors)
    _set_status(db, config, ComparisonRunStatus.COMPLETED, None)


def _run_or_none(db: Session, run_id: int) -> Run | None:
    return db.query(Run).filter(Run.id == run_id).first()


def _config_or_none(db: Session, run_id: int) -> RunComparisonConfig | None:
    return db.query(RunComparisonConfig).filter(RunComparisonConfig.run_id == run_id).first()


def _set_status(db: Session, config: RunComparisonConfig, status: ComparisonRunStatus, error: str | None) -> None:
    config.status = status
    config.error_message = error
    if status in {ComparisonRunStatus.COMPLETED, ComparisonRunStatus.FAILED, ComparisonRunStatus.SKIPPED}:
        config.completed_at = datetime.utcnow()
    db.commit()


async def _run_pipeline(
    db: Session,
    run: Run,
    config: RunComparisonConfig,
    k_products: int,
    top_competitors: int,
) -> None:
    competitors = _competitor_brands(db, run.id, config.primary_brand_id, config.competitor_brands, top_competitors)
    primary_products = _top_products_for_brand(db, run.id, config.primary_brand_id, k_products)
    competitor_products = _competitor_products(db, run.id, competitors, k_products, set(config.competitor_brands or []))
    await _ensure_generated_prompts(db, run, config, competitors, primary_products, competitor_products)
    answers = await _ensure_answers(db, run, config)
    await _refresh_observations(db, run, answers)


def _competitor_brands(
    db: Session,
    run_id: int,
    primary_brand_id: int,
    user_competitor_names: list[str],
    top_n: int,
) -> list[Brand]:
    by_dvs = _top_competitors_by_dvs(db, run_id, primary_brand_id, top_n)
    by_name = _ensure_competitor_brands(db, primary_brand_id, user_competitor_names)
    seen = {primary_brand_id}
    out: list[Brand] = []
    for b in by_name + by_dvs:
        if b.id in seen:
            continue
        seen.add(b.id)
        out.append(b)
    return out


def _ensure_competitor_brands(db: Session, primary_brand_id: int, names: list[str]) -> list[Brand]:
    primary = db.query(Brand).filter(Brand.id == primary_brand_id).first()
    vertical_id = primary.vertical_id if primary else None
    return [_get_or_create_brand(db, vertical_id, n) for n in names if n and vertical_id]


def _get_or_create_brand(db: Session, vertical_id: int, name: str) -> Brand:
    found = db.query(Brand).filter(Brand.vertical_id == vertical_id, func.lower(Brand.display_name) == name.lower()).first()
    if found:
        return found
    brand = Brand(vertical_id=vertical_id, display_name=name, original_name=name, translated_name=None, aliases={"zh": [], "en": []}, is_user_input=True)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


def _top_competitors_by_dvs(db: Session, run_id: int, primary_brand_id: int, top_n: int) -> list[Brand]:
    rows = (
        db.query(RunMetrics.brand_id)
        .filter(RunMetrics.run_id == run_id, RunMetrics.brand_id != primary_brand_id)
        .order_by(RunMetrics.dragon_lens_visibility.desc())
        .limit(max(0, int(top_n)))
        .all()
    )
    ids = [int(r[0]) for r in rows]
    return db.query(Brand).filter(Brand.id.in_(ids)).all() if ids else []


def _top_products_for_brand(db: Session, run_id: int, brand_id: int, k: int) -> list[Product]:
    ranked = (
        db.query(Product)
        .join(RunProductMetrics, RunProductMetrics.product_id == Product.id)
        .filter(RunProductMetrics.run_id == run_id, Product.brand_id == brand_id)
        .order_by(RunProductMetrics.dragon_lens_visibility.desc())
        .limit(max(0, int(k)))
        .all()
    )
    if ranked:
        return ranked
    rows = (
        db.query(Product.id, func.count(ProductMention.id))
        .join(ProductMention, ProductMention.product_id == Product.id)
        .join(LLMAnswer, LLMAnswer.id == ProductMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id, Product.brand_id == brand_id, ProductMention.mentioned)
        .group_by(Product.id)
        .order_by(func.count(ProductMention.id).desc())
        .limit(max(0, int(k)))
        .all()
    )
    ids = [int(r[0]) for r in rows]
    return db.query(Product).filter(Product.id.in_(ids)).all() if ids else []


def _competitor_products(db: Session, run_id: int, competitors: list[Brand], k: int, user_competitors: set[str]) -> dict[int, list[Product]]:
    out: dict[int, list[Product]] = {}
    for b in competitors:
        products = _top_products_for_brand(db, run_id, b.id, k)
        out[b.id] = products
        if not products and b.display_name in user_competitors:
            _add_event(
                db,
                run_id,
                "info",
                "no_competitor_products",
                f"No products mentioned for competitor '{b.display_name}', skipping product comparison",
                {"competitor_brand": b.display_name},
            )
    return out


def _add_event(db: Session, run_id: int, level: str, code: str, message: str, payload: dict | None) -> None:
    db.add(ComparisonRunEvent(run_id=run_id, level=level, code=code, message=message, payload=payload))
    db.commit()


async def _ensure_generated_prompts(
    db: Session,
    run: Run,
    config: RunComparisonConfig,
    competitors: list[Brand],
    primary_products: list[Product],
    competitor_products: dict[int, list[Product]],
) -> None:
    user_prompts = _existing_user_prompts(db, run.id)
    missing = competitor_missing_counts(list(config.competitor_brands or []), _competitor_prompt_counts(db, run.id), config.min_prompts_per_competitor)
    requested = total_generation_count(config.target_count, len(user_prompts), missing)
    if requested <= 0 or not config.autogenerate_missing:
        return
    context = _generation_context(db, run, config, competitors, primary_products, competitor_products, user_prompts)
    await _generate_and_store(db, run, context, requested)


def _existing_user_prompts(db: Session, run_id: int) -> list[ComparisonPrompt]:
    return db.query(ComparisonPrompt).filter(ComparisonPrompt.run_id == run_id, ComparisonPrompt.source == ComparisonPromptSource.USER).all()


def _competitor_prompt_counts(db: Session, run_id: int) -> dict[str, int]:
    rows = (
        db.query(Brand.display_name, func.count(ComparisonPrompt.id))
        .join(ComparisonPrompt, ComparisonPrompt.competitor_brand_id == Brand.id)
        .filter(ComparisonPrompt.run_id == run_id)
        .group_by(Brand.display_name)
        .all()
    )
    return {str(name): int(count) for name, count in rows}


def _generation_context(
    db: Session,
    run: Run,
    config: RunComparisonConfig,
    competitors: list[Brand],
    primary_products: list[Product],
    competitor_products: dict[int, list[Product]],
    user_prompts: list[ComparisonPrompt],
) -> dict:
    primary_brand = db.query(Brand).filter(Brand.id == config.primary_brand_id).first()
    return {
        "vertical_name": primary_brand.vertical.name if primary_brand and primary_brand.vertical else "",
        "vertical_description": primary_brand.vertical.description if primary_brand and primary_brand.vertical else "",
        "primary_brand": primary_brand.display_name if primary_brand else "",
        "competitor_brands": [b.display_name for b in competitors],
        "user_competitor_brands": list(config.competitor_brands or []),
        "min_prompts_per_user_competitor": int(config.min_prompts_per_competitor),
        "primary_products": [p.display_name for p in primary_products],
        "competitor_products": {b.display_name: [p.display_name for p in competitor_products.get(b.id, [])] for b in competitors},
        "user_prompts": [{"text_zh": p.text_zh, "text_en": p.text_en} for p in user_prompts],
    }


async def _generate_and_store(db: Session, run: Run, context: dict, requested: int) -> None:
    llm_router = LLMRouter(db)
    resolution = llm_router.resolve(run.provider, run.model_name)
    prompt_zh = build_comparison_prompt_generation_prompt(context, requested)
    answer_zh, _, _, _ = await llm_router.query_with_resolution(resolution, prompt_zh)
    items = parse_comparison_prompts_from_text(answer_zh)
    _store_generated_prompts(db, run, items)


def _store_generated_prompts(db: Session, run: Run, items: list[dict]) -> None:
    for item in items:
        prompt = _comparison_prompt_from_item(db, run, item)
        if prompt:
            db.add(prompt)
    db.commit()


def _comparison_prompt_from_item(db: Session, run: Run, item: dict) -> ComparisonPrompt | None:
    if not item.get("text_zh"):
        return None
    prompt_type = ComparisonPromptType(item.get("prompt_type"))
    primary_brand_id = _brand_id_by_name(db, run.vertical_id, item.get("primary_brand")) or None
    competitor_brand_id = _brand_id_by_name(db, run.vertical_id, item.get("competitor_brand")) or None
    primary_product_id = _product_id_by_name(db, run.vertical_id, item.get("primary_product")) or None
    competitor_product_id = _product_id_by_name(db, run.vertical_id, item.get("competitor_product")) or None
    return ComparisonPrompt(
        run_id=run.id,
        vertical_id=run.vertical_id,
        prompt_type=prompt_type,
        source=ComparisonPromptSource.GENERATED,
        text_zh=item.get("text_zh"),
        text_en=item.get("text_en"),
        primary_brand_id=primary_brand_id,
        competitor_brand_id=competitor_brand_id,
        primary_product_id=primary_product_id if prompt_type == ComparisonPromptType.PRODUCT_VS_PRODUCT else None,
        competitor_product_id=competitor_product_id if prompt_type == ComparisonPromptType.PRODUCT_VS_PRODUCT else None,
        aspects=item.get("aspects") or [],
    )


def _brand_id_by_name(db: Session, vertical_id: int, name: str | None) -> int | None:
    if not name:
        return None
    row = db.query(Brand.id).filter(Brand.vertical_id == vertical_id, func.lower(Brand.display_name) == name.lower()).first()
    return int(row[0]) if row else None


def _product_id_by_name(db: Session, vertical_id: int, name: str | None) -> int | None:
    if not name:
        return None
    row = db.query(Product.id).filter(Product.vertical_id == vertical_id, func.lower(Product.display_name) == name.lower()).first()
    return int(row[0]) if row else None


async def _ensure_answers(db: Session, run: Run, config: RunComparisonConfig) -> list[ComparisonAnswer]:
    prompts = db.query(ComparisonPrompt).filter(ComparisonPrompt.run_id == run.id).all()
    translator = TranslaterService()
    llm_router = LLMRouter(db)
    resolution = llm_router.resolve(run.provider, run.model_name)
    return await _fetch_answers(db, run, prompts, llm_router, resolution, translator)


async def _fetch_answers(db: Session, run: Run, prompts: list[ComparisonPrompt], llm_router, resolution, translator) -> list[ComparisonAnswer]:
    sem = asyncio.Semaphore(3)
    tasks = [_fetch_one(db, run, p, llm_router, resolution, translator, sem) for p in prompts]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r]


async def _fetch_one(db: Session, run: Run, prompt: ComparisonPrompt, llm_router, resolution, translator, sem: asyncio.Semaphore) -> ComparisonAnswer | None:
    existing = db.query(ComparisonAnswer).filter(ComparisonAnswer.run_id == run.id, ComparisonAnswer.comparison_prompt_id == prompt.id).first()
    if existing:
        return existing
    prompt_zh = prompt.text_zh or await translator.translate_text(prompt.text_en or "", "English", "Chinese")
    async with sem:
        answer_zh, tokens_in, tokens_out, latency = await llm_router.query_with_resolution(resolution, prompt_zh)
    answer_en = await translator.translate_text(answer_zh, "Chinese", "English") if answer_zh else None
    ans = ComparisonAnswer(run_id=run.id, comparison_prompt_id=prompt.id, provider=run.provider, model_name=run.model_name, route=resolution.route, raw_answer_zh=answer_zh or "", raw_answer_en=answer_en, tokens_in=tokens_in, tokens_out=tokens_out, latency=latency, cost_estimate=None)
    db.add(ans)
    db.commit()
    db.refresh(ans)
    return ans


async def _refresh_observations(db: Session, run: Run, answers: list[ComparisonAnswer]) -> None:
    ollama = OllamaService()
    translator = TranslaterService()
    for answer in answers:
        db.query(ComparisonSentimentObservation).filter(ComparisonSentimentObservation.comparison_answer_id == answer.id).delete()
        await _store_answer_observations(db, run, answer, ollama, translator)
    db.commit()


async def _store_answer_observations(db: Session, run: Run, answer: ComparisonAnswer, ollama: OllamaService, translator: TranslaterService) -> None:
    prompt = db.query(ComparisonPrompt).filter(ComparisonPrompt.id == answer.comparison_prompt_id).first()
    if not prompt:
        return
    await _store_brand_observations(db, run, prompt, answer, ollama, translator)
    await _store_product_observations(db, run, prompt, answer, ollama, translator)


async def _store_brand_observations(db: Session, run: Run, prompt: ComparisonPrompt, answer: ComparisonAnswer, ollama: OllamaService, translator: TranslaterService) -> None:
    brand_ids = [i for i in [prompt.primary_brand_id, prompt.competitor_brand_id] if i]
    brands = db.query(Brand).filter(Brand.id.in_(brand_ids)).all() if brand_ids else []
    if not brands:
        return
    names, aliases = _entity_variants(brands)
    mentions = await ollama.extract_brands(answer.raw_answer_zh, names, aliases)
    await _mentions_to_observations(db, run.id, answer.id, mentions, brands, EntityType.BRAND, translator, ollama, prompt)


async def _store_product_observations(db: Session, run: Run, prompt: ComparisonPrompt, answer: ComparisonAnswer, ollama: OllamaService, translator: TranslaterService) -> None:
    product_ids = [i for i in [prompt.primary_product_id, prompt.competitor_product_id] if i]
    products = db.query(Product).filter(Product.id.in_(product_ids)).all() if product_ids else []
    if not products:
        return
    names = [p.display_name for p in products]
    aliases = [[p.display_name, p.original_name or "", p.translated_name or ""] for p in products]
    mentions = await ollama.extract_products(answer.raw_answer_zh, names, aliases, [], [])
    await _product_mentions_to_observations(db, run.id, answer.id, mentions, products, translator, ollama, prompt)


def _entity_variants(brands: list[Brand]) -> tuple[list[str], list[list[str]]]:
    names = [b.display_name for b in brands]
    aliases = [[b.original_name or "", b.translated_name or "", *list((b.aliases or {}).get("zh", [])), *list((b.aliases or {}).get("en", []))] for b in brands]
    return names, aliases


async def _mentions_to_observations(
    db: Session,
    run_id: int,
    answer_id: int,
    mentions: list[dict],
    brands: list[Brand],
    entity_type: EntityType,
    translator: TranslaterService,
    ollama: OllamaService,
    prompt: ComparisonPrompt,
) -> None:
    for m in mentions:
        if not m.get("mentioned"):
            continue
        idx = int(m.get("brand_index"))
        if idx < 0 or idx >= len(brands):
            continue
        brand = brands[idx]
        role = _role_for_brand(prompt, brand.id)
        await _snippets_to_observations(db, run_id, answer_id, entity_type, brand.id, role, m.get("snippets") or [], translator, ollama)


async def _product_mentions_to_observations(
    db: Session,
    run_id: int,
    answer_id: int,
    mentions: list[dict],
    products: list[Product],
    translator: TranslaterService,
    ollama: OllamaService,
    prompt: ComparisonPrompt,
) -> None:
    for m in mentions:
        if not m.get("mentioned"):
            continue
        idx = int(m.get("product_index"))
        if idx < 0 or idx >= len(products):
            continue
        product = products[idx]
        role = _role_for_product(prompt, product.id)
        await _snippets_to_observations(db, run_id, answer_id, EntityType.PRODUCT, product.id, role, m.get("snippets") or [], translator, ollama)


def _role_for_brand(prompt: ComparisonPrompt, brand_id: int) -> ComparisonEntityRole:
    if prompt.primary_brand_id == brand_id:
        return ComparisonEntityRole.PRIMARY
    return ComparisonEntityRole.COMPETITOR


def _role_for_product(prompt: ComparisonPrompt, product_id: int) -> ComparisonEntityRole:
    if prompt.primary_product_id == product_id:
        return ComparisonEntityRole.PRIMARY
    return ComparisonEntityRole.COMPETITOR


async def _snippets_to_observations(
    db: Session,
    run_id: int,
    answer_id: int,
    entity_type: EntityType,
    entity_id: int,
    role: ComparisonEntityRole,
    snippets: list[str],
    translator: TranslaterService,
    ollama: OllamaService,
) -> None:
    for s in [sn for sn in snippets if sn][:3]:
        sentiment = await _sentiment_for_snippet(ollama, s)
        translated = await translator.translate_text(s, "Chinese", "English")
        db.add(ComparisonSentimentObservation(
            run_id=run_id,
            comparison_answer_id=answer_id,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_role=role,
            aspect=None,
            sentiment=sentiment,
            snippet_zh=s,
            snippet_en=translated,
        ))


async def _sentiment_for_snippet(ollama: OllamaService, snippet_zh: str) -> Sentiment:
    raw = (await ollama.classify_sentiment(snippet_zh)).strip().lower()
    if raw == "positive":
        return Sentiment.POSITIVE
    if raw == "negative":
        return Sentiment.NEGATIVE
    return Sentiment.NEUTRAL
