from __future__ import annotations

import asyncio
import logging
from datetime import datetime

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
    Product,
    PromptLanguage,
    Run,
    RunComparisonConfig,
    RunMetrics,
    RunProductMetrics,
    Sentiment,
)
from services.comparison_prompts.generation import build_product_comparison_prompt_generation_prompt
from services.comparison_prompts.pair_planner import build_competitor_brand_schedule
from services.comparison_prompts.text_parser import parse_text_zh_list_from_text
from services.ollama import OllamaService
from services.remote_llms import LLMRouter
from services.translater import TranslaterService

logger = logging.getLogger(__name__)


async def run_comparison_pipeline(db: Session, run_id: int) -> None:
    run = _run_or_none(db, run_id)
    config = _config_or_none(db, run_id)
    if not run or not config or not config.enabled:
        return
    if config.status == ComparisonRunStatus.COMPLETED:
        return
    _set_status(db, config, ComparisonRunStatus.IN_PROGRESS, None)
    try:
        status = await _run_pipeline(db, run, config)
    except Exception as exc:
        _set_status(db, config, ComparisonRunStatus.FAILED, str(exc))
        raise
    _set_status(db, config, status, None)


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


async def _run_pipeline(db: Session, run: Run, config: RunComparisonConfig) -> ComparisonRunStatus:
    plan = _pair_plan(db, run.id, config.primary_brand_id, config.target_count)
    if not plan:
        _add_event(db, run.id, "info", "comparison_skipped", "Comparison skipped (insufficient mapped competitors)", None)
        return ComparisonRunStatus.SKIPPED
    await _ensure_prompts(db, run, config, plan)
    answers = await _ensure_answers(db, run)
    await _refresh_observations(db, run, answers)
    await _translate_comparison_outputs(db, run.id)
    return ComparisonRunStatus.COMPLETED


def _pair_plan(db: Session, run_id: int, primary_brand_id: int, total: int) -> list[dict]:
    products = _products_by_brand(db, run_id)
    primary = products.get(int(primary_brand_id), [])
    competitors = _competitor_brand_ids(db, run_id, primary_brand_id, list(products.keys()))
    schedule = build_competitor_brand_schedule(competitors, total=total, max_per_brand=3)
    return _pairs_from_schedule(primary, products, schedule, _aspects())


def _products_by_brand(db: Session, run_id: int) -> dict[int, list[Product]]:
    rows = (
        db.query(Product)
        .join(RunProductMetrics, RunProductMetrics.product_id == Product.id)
        .filter(RunProductMetrics.run_id == run_id, Product.brand_id.isnot(None))
        .order_by(RunProductMetrics.dragon_lens_visibility.desc())
        .all()
    )
    return _group_products(rows)


def _group_products(products: list[Product]) -> dict[int, list[Product]]:
    out: dict[int, list[Product]] = {}
    for p in products:
        out.setdefault(int(p.brand_id), []).append(p)
    return out


def _competitor_brand_ids(db: Session, run_id: int, primary_brand_id: int, brand_ids: list[int]) -> list[int]:
    rows = (
        db.query(RunMetrics.brand_id)
        .filter(RunMetrics.run_id == run_id, RunMetrics.brand_id != primary_brand_id, RunMetrics.brand_id.in_(brand_ids))
        .order_by(RunMetrics.dragon_lens_visibility.desc())
        .all()
    )
    ordered = [int(r[0]) for r in rows]
    seen = set(ordered)
    extras = [int(b) for b in brand_ids if int(b) != int(primary_brand_id) and int(b) not in seen]
    return ordered + sorted(extras)


def _pairs_from_schedule(
    primary_products: list[Product],
    products_by_brand: dict[int, list[Product]],
    competitor_schedule: list[int],
    aspects: list[str],
) -> list[dict]:
    if not primary_products or not competitor_schedule:
        return []
    usage: dict[int, int] = {}
    out: list[dict] = []
    for idx, brand_id in enumerate(competitor_schedule):
        pair = _pair_spec(primary_products, products_by_brand, aspects, usage, idx, brand_id)
        if not pair:
            return []
        out.append(pair)
    return out


def _pair_spec(
    primary_products: list[Product],
    products_by_brand: dict[int, list[Product]],
    aspects: list[str],
    usage: dict[int, int],
    idx: int,
    competitor_brand_id: int,
) -> dict | None:
    comp = products_by_brand.get(int(competitor_brand_id), [])
    if not comp:
        return None
    usage[competitor_brand_id] = usage.get(competitor_brand_id, 0) + 1
    return {
        "primary_product": primary_products[idx % len(primary_products)],
        "competitor_product": comp[(usage[competitor_brand_id] - 1) % len(comp)],
        "aspect_zh": aspects[idx % len(aspects)],
    }


def _aspects() -> list[str]:
    return ["油耗", "空间", "舒适性", "安全性", "性价比", "可靠性", "售后", "做工用料", "动力表现", "保值率"]


async def _ensure_prompts(db: Session, run: Run, config: RunComparisonConfig, plan: list[dict]) -> None:
    existing = db.query(ComparisonPrompt).filter(ComparisonPrompt.run_id == run.id).count()
    if existing:
        return
    pairs = _pairs_payload(db, run.vertical_id, plan)
    if len(pairs) != len(plan) or len(pairs) != int(config.target_count):
        raise ValueError("comparison prompt planning failed")
    texts = await _generate_prompt_texts(pairs)
    _store_prompts(db, run, plan, pairs, texts)


def _pairs_payload(db: Session, vertical_id: int, plan: list[dict]) -> list[dict]:
    brands = _brand_names(db, vertical_id)
    out: list[dict] = []
    for item in plan:
        primary: Product = item["primary_product"]
        competitor: Product = item["competitor_product"]
        out.append(_pair_payload(brands, primary, competitor, item["aspect_zh"]))
    return out


def _brand_names(db: Session, vertical_id: int) -> dict[int, str]:
    rows = db.query(Brand.id, Brand.display_name).filter(Brand.vertical_id == vertical_id).all()
    return {int(i): str(n) for i, n in rows}


def _pair_payload(brands: dict[int, str], primary: Product, competitor: Product, aspect_zh: str) -> dict:
    return {
        "primary_brand": brands.get(int(primary.brand_id), ""),
        "primary_product": primary.display_name,
        "competitor_brand": brands.get(int(competitor.brand_id), ""),
        "competitor_product": competitor.display_name,
        "aspect_zh": str(aspect_zh),
    }


async def _generate_prompt_texts(pairs: list[dict]) -> list[str]:
    prompt = build_product_comparison_prompt_generation_prompt(pairs)
    ollama = OllamaService()
    raw = await ollama._call_ollama(model=ollama.main_model, prompt=prompt, temperature=0.2)
    texts = parse_text_zh_list_from_text(raw)
    return texts if _texts_match_pairs(texts, pairs) else []


def _texts_match_pairs(texts: list[str], pairs: list[dict]) -> bool:
    if len(texts) != len(pairs) or not texts:
        return False
    return all(_valid_prompt(t, p) for t, p in zip(texts, pairs))


def _valid_prompt(text: str, pair: dict) -> bool:
    required = [pair.get("primary_product"), pair.get("competitor_product"), pair.get("aspect_zh")]
    return all(str(r) in (text or "") for r in required if r)


def _store_prompts(db: Session, run: Run, plan: list[dict], pairs: list[dict], texts: list[str]) -> None:
    if not texts:
        raise ValueError("comparison prompt generation failed")
    for item, pair, text_zh in zip(plan, pairs, texts):
        prompt = _prompt_row(run, item, pair, text_zh)
        db.add(prompt)
    db.commit()


def _prompt_row(run: Run, item: dict, pair: dict, text_zh: str) -> ComparisonPrompt:
    primary_product: Product = item["primary_product"]
    competitor_product: Product = item["competitor_product"]
    return ComparisonPrompt(
        run_id=run.id,
        vertical_id=run.vertical_id,
        prompt_type=ComparisonPromptType.PRODUCT_VS_PRODUCT,
        source=ComparisonPromptSource.GENERATED,
        text_zh=str(text_zh),
        text_en=None,
        language_original=PromptLanguage.ZH,
        primary_brand_id=int(primary_product.brand_id),
        competitor_brand_id=int(competitor_product.brand_id),
        primary_product_id=int(primary_product.id),
        competitor_product_id=int(competitor_product.id),
        aspects=[pair.get("aspect_zh")] if pair.get("aspect_zh") else [],
    )


async def _ensure_answers(db: Session, run: Run) -> list[ComparisonAnswer]:
    prompts = db.query(ComparisonPrompt).filter(ComparisonPrompt.run_id == run.id).all()
    llm_router = LLMRouter(db)
    resolution = llm_router.resolve(run.provider, run.model_name)
    return await _fetch_answers(db, run, prompts, llm_router, resolution)


async def _fetch_answers(db: Session, run: Run, prompts: list[ComparisonPrompt], llm_router, resolution) -> list[ComparisonAnswer]:
    sem = asyncio.Semaphore(3)
    tasks = [_fetch_one(db, run, p, llm_router, resolution, sem) for p in prompts]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r]


async def _fetch_one(db: Session, run: Run, prompt: ComparisonPrompt, llm_router, resolution, sem: asyncio.Semaphore) -> ComparisonAnswer | None:
    existing = db.query(ComparisonAnswer).filter(ComparisonAnswer.run_id == run.id, ComparisonAnswer.comparison_prompt_id == prompt.id).first()
    if existing:
        return existing
    if not prompt.text_zh:
        return None
    async with sem:
        answer_zh, tokens_in, tokens_out, latency = await llm_router.query_with_resolution(resolution, prompt.text_zh)
    ans = ComparisonAnswer(
        run_id=run.id,
        comparison_prompt_id=prompt.id,
        provider=run.provider,
        model_name=run.model_name,
        route=resolution.route,
        raw_answer_zh=answer_zh or "",
        raw_answer_en=None,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        latency=latency,
        cost_estimate=None,
    )
    db.add(ans)
    db.commit()
    db.refresh(ans)
    return ans


async def _refresh_observations(db: Session, run: Run, answers: list[ComparisonAnswer]) -> None:
    ollama = OllamaService()
    for answer in answers:
        db.query(ComparisonSentimentObservation).filter(ComparisonSentimentObservation.comparison_answer_id == answer.id).delete()
        await _store_product_observations(db, run, answer, ollama)
    db.commit()


async def _store_product_observations(db: Session, run: Run, answer: ComparisonAnswer, ollama: OllamaService) -> None:
    prompt = db.query(ComparisonPrompt).filter(ComparisonPrompt.id == answer.comparison_prompt_id).first()
    if not prompt:
        return
    products = _prompt_products(db, prompt)
    mentions = await _extract_products(ollama, answer.raw_answer_zh, products)
    await _mentions_to_observations(db, run.id, answer.id, prompt, products, mentions, ollama)


def _prompt_products(db: Session, prompt: ComparisonPrompt) -> list[Product]:
    ids = [i for i in [prompt.primary_product_id, prompt.competitor_product_id] if i]
    return db.query(Product).filter(Product.id.in_(ids)).all() if ids else []


async def _extract_products(ollama: OllamaService, text_zh: str, products: list[Product]) -> list[dict]:
    names = [p.display_name for p in products]
    aliases = [[p.display_name, p.original_name or "", p.translated_name or ""] for p in products]
    return await ollama.extract_products(text_zh, names, aliases, [], [])


async def _mentions_to_observations(
    db: Session,
    run_id: int,
    answer_id: int,
    prompt: ComparisonPrompt,
    products: list[Product],
    mentions: list[dict],
    ollama: OllamaService,
) -> None:
    for m in mentions:
        if not m.get("mentioned"):
            continue
        idx = int(m.get("product_index"))
        if idx < 0 or idx >= len(products):
            continue
        product = products[idx]
        role = _role_for_product(prompt, product.id)
        await _snippets_to_observations(db, run_id, answer_id, product, role, m.get("snippets") or [], ollama)


def _role_for_product(prompt: ComparisonPrompt, product_id: int) -> ComparisonEntityRole:
    if prompt.primary_product_id == product_id:
        return ComparisonEntityRole.PRIMARY
    return ComparisonEntityRole.COMPETITOR


async def _snippets_to_observations(
    db: Session,
    run_id: int,
    answer_id: int,
    product: Product,
    role: ComparisonEntityRole,
    snippets: list[str],
    ollama: OllamaService,
) -> None:
    for snippet in [s for s in snippets if s][:3]:
        sentiment = await _sentiment_for_snippet(ollama, snippet)
        _add_obs(db, run_id, answer_id, EntityType.PRODUCT, int(product.id), role, sentiment, snippet, "")
        if product.brand_id:
            _add_obs(db, run_id, answer_id, EntityType.BRAND, int(product.brand_id), role, sentiment, snippet, "")


def _add_obs(
    db: Session,
    run_id: int,
    answer_id: int,
    entity_type: EntityType,
    entity_id: int,
    role: ComparisonEntityRole,
    sentiment: Sentiment,
    snippet_zh: str,
    snippet_en: str,
) -> None:
    db.add(ComparisonSentimentObservation(
        run_id=run_id,
        comparison_answer_id=answer_id,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_role=role,
        aspect=None,
        sentiment=sentiment,
        snippet_zh=snippet_zh,
        snippet_en=snippet_en,
    ))


async def _sentiment_for_snippet(ollama: OllamaService, snippet_zh: str) -> Sentiment:
    raw = (await ollama.classify_sentiment(snippet_zh)).strip().lower()
    if raw == "positive":
        return Sentiment.POSITIVE
    if raw == "negative":
        return Sentiment.NEGATIVE
    return Sentiment.NEUTRAL


async def _translate_comparison_outputs(db: Session, run_id: int) -> None:
    translator = TranslaterService()
    await _translate_prompts(db, run_id, translator)
    await _translate_answers(db, run_id, translator)
    await _translate_snippets(db, run_id, translator)
    db.commit()


async def _translate_prompts(db: Session, run_id: int, translator: TranslaterService) -> None:
    prompts = db.query(ComparisonPrompt).filter(ComparisonPrompt.run_id == run_id).all()
    texts = [p.text_zh or "" for p in prompts]
    translated = await translator.translate_batch(texts, "Chinese", "English")
    for p, en in zip(prompts, translated):
        p.text_en = en


async def _translate_answers(db: Session, run_id: int, translator: TranslaterService) -> None:
    answers = db.query(ComparisonAnswer).filter(ComparisonAnswer.run_id == run_id).all()
    texts = [a.raw_answer_zh or "" for a in answers]
    translated = await translator.translate_batch(texts, "Chinese", "English")
    for a, en in zip(answers, translated):
        a.raw_answer_en = en


async def _translate_snippets(db: Session, run_id: int, translator: TranslaterService) -> None:
    rows = db.query(ComparisonSentimentObservation).filter(ComparisonSentimentObservation.run_id == run_id).all()
    texts = [r.snippet_zh or "" for r in rows]
    translated = await translator.translate_batch(texts, "Chinese", "English")
    for r, en in zip(rows, translated):
        r.snippet_en = en


def _add_event(db: Session, run_id: int, level: str, code: str, message: str, payload: dict | None) -> None:
    db.add(ComparisonRunEvent(run_id=run_id, level=level, code=code, message=message, payload=payload))
    db.commit()
