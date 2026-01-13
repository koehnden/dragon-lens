"""API router for metrics retrieval."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from models import (
    Brand,
    BrandMention,
    ComparisonAnswer,
    ComparisonPrompt,
    ComparisonRunEvent,
    ComparisonRunStatus,
    ComparisonSentimentObservation,
    DailyMetrics,
    EntityType,
    LLMAnswer,
    Product,
    ProductMention,
    Prompt,
    Run,
    RunComparisonConfig,
    RunMetrics,
    RunProductMetrics,
    Sentiment,
    Vertical,
    get_db,
)
from metrics.metrics import AnswerMetrics, visibility_metrics
from models.schemas import (
    AllRunMetricsResponse,
    AllRunProductMetricsResponse,
    BrandMetrics,
    ComparisonEvidenceSnippet,
    ComparisonEntitySentimentSummary,
    ComparisonCharacteristicSummary,
    ComparisonPromptOutcomeDetail,
    MetricsResponse,
    ProductMetrics,
    ProductMetricsResponse,
    RunComparisonMessage,
    RunComparisonMetricsResponse,
    RunComparisonSummaryResponse,
    RunMetricsResponse,
)
from services.translater import format_entity_label
from services.canonicalization_metrics import (
    build_brand_canonical_maps,
    build_product_canonical_maps,
    build_user_brand_variant_maps,
    choose_brand_rep,
    choose_product_rep,
    normalize_entity_key,
    resolve_brand_key,
    resolve_canonical_key,
)

router = APIRouter()


def get_vertical_or_raise(db: Session, vertical_id: int) -> Vertical:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {vertical_id} not found")
    return vertical


def validate_brand_belongs_to_vertical(
    db: Session, brand_id: int, vertical_id: int
) -> Brand:
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand or brand.vertical_id != vertical_id:
        detail = f"Brand {brand_id} not found in vertical {vertical_id}"
        raise HTTPException(status_code=404, detail=detail)
    return brand


def validate_date_range(
    start_date: Optional[datetime], end_date: Optional[datetime]
) -> None:
    if start_date and end_date and start_date > end_date:
        detail = "start_date must be on or before end_date"
        raise HTTPException(status_code=400, detail=detail)


@router.get("/latest", response_model=MetricsResponse)
async def get_latest_metrics(
    vertical_id: int = Query(..., description="Vertical ID"),
    model_name: str = Query("all", description="Model name or 'all' for aggregated"),
    db: Session = Depends(get_db),
) -> MetricsResponse:
    vertical = get_vertical_or_raise(db, vertical_id)
    brand_id_to_key, brand_groups = _brand_groups(db, vertical_id)

    if model_name == "all":
        runs, display_model = _get_all_model_runs(db, vertical_id)
    else:
        runs, display_model = _get_single_model_runs(db, vertical_id, model_name)

    if not runs:
        detail = f"No runs found for vertical {vertical_id}"
        if model_name != "all":
            detail += f" and model {model_name}"
        raise HTTPException(status_code=404, detail=detail)

    run_ids = [r.id for r in runs]
    latest_run_time = max(r.run_time for r in runs)

    prompts = db.query(Prompt).filter(Prompt.vertical_id == vertical_id).all()
    prompt_ids = [p.id for p in prompts]
    mentions = (
        db.query(BrandMention)
        .join(LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id)
        .filter(LLMAnswer.run_id.in_(run_ids))
        .all()
    )
    answer_metrics = _collapse_answer_metrics(_brand_answer_metrics(mentions, brand_id_to_key))

    brand_metrics = []
    keys = _brand_keys(answer_metrics, brand_groups)
    for key in keys:
        rep_brand = choose_brand_rep(brand_groups[key])
        competitors = [k for k in keys if k != key]
        metrics = visibility_metrics(
            prompt_ids=prompt_ids,
            mentions=answer_metrics,
            brand=key,
            competitor_brands=competitors,
        )

        brand_metrics.append(
            BrandMetrics(
                brand_id=rep_brand.id,
                brand_name=format_entity_label(rep_brand.original_name, rep_brand.translated_name),
                mention_rate=metrics["mention_rate"],
                share_of_voice=metrics["share_of_voice"],
                top_spot_share=metrics["top_spot_share"],
                sentiment_index=metrics["sentiment_index"],
                dragon_lens_visibility=metrics["dragon_lens_visibility"],
            )
        )

    return MetricsResponse(
        vertical_id=vertical_id,
        vertical_name=vertical.name,
        model_name=display_model,
        date=latest_run_time,
        brands=brand_metrics,
    )


@router.get("/latest/products", response_model=ProductMetricsResponse)
async def get_latest_product_metrics(
    vertical_id: int = Query(..., description="Vertical ID"),
    model_name: str = Query("all", description="Model name or 'all' for aggregated"),
    db: Session = Depends(get_db),
) -> ProductMetricsResponse:
    vertical = get_vertical_or_raise(db, vertical_id)
    product_id_to_key, product_groups = _product_groups(db, vertical_id)

    if model_name == "all":
        runs, display_model = _get_all_model_runs(db, vertical_id)
    else:
        runs, display_model = _get_single_model_runs(db, vertical_id, model_name)

    if not runs:
        detail = f"No runs found for vertical {vertical_id}"
        if model_name != "all":
            detail += f" and model {model_name}"
        raise HTTPException(status_code=404, detail=detail)

    run_ids = [r.id for r in runs]
    latest_run_time = max(r.run_time for r in runs)

    prompts = db.query(Prompt).filter(Prompt.vertical_id == vertical_id).all()
    prompt_ids = [p.id for p in prompts]

    mentions = (
        db.query(ProductMention)
        .join(LLMAnswer, LLMAnswer.id == ProductMention.llm_answer_id)
        .filter(LLMAnswer.run_id.in_(run_ids))
        .all()
    )

    answer_metrics = _collapse_answer_metrics(_product_answer_metrics(mentions, product_id_to_key))

    product_metrics = []
    keys = _product_keys(answer_metrics, product_groups)
    for key in keys:
        rep_product = choose_product_rep(product_groups[key])
        competitors = [k for k in keys if k != key]
        metrics = visibility_metrics(
            prompt_ids=prompt_ids,
            mentions=answer_metrics,
            brand=key,
            competitor_brands=competitors,
        )

        brand_name = ""
        if rep_product.brand:
            brand_name = format_entity_label(
                rep_product.brand.original_name, rep_product.brand.translated_name
            )

        product_metrics.append(
            ProductMetrics(
                product_id=rep_product.id,
                product_name=format_entity_label(
                    rep_product.original_name, rep_product.translated_name
                ),
                brand_id=rep_product.brand_id,
                brand_name=brand_name,
                mention_rate=metrics["mention_rate"],
                share_of_voice=metrics["share_of_voice"],
                top_spot_share=metrics["top_spot_share"],
                sentiment_index=metrics["sentiment_index"],
                dragon_lens_visibility=metrics["dragon_lens_visibility"],
            )
        )

    return ProductMetricsResponse(
        vertical_id=vertical_id,
        vertical_name=vertical.name,
        model_name=display_model,
        date=latest_run_time,
        products=product_metrics,
    )


def _get_all_model_runs(db: Session, vertical_id: int) -> tuple[list, str]:
    runs = (
        db.query(Run)
        .filter(Run.vertical_id == vertical_id, Run.answers.any())
        .order_by(Run.run_time.desc())
        .all()
    )

    if not runs:
        runs = (
            db.query(Run)
            .filter(Run.vertical_id == vertical_id)
            .order_by(Run.run_time.desc())
            .all()
        )

    return runs, "All Models"


def _get_single_model_runs(db: Session, vertical_id: int, model_name: str) -> tuple[list, str]:
    runs = (
        db.query(Run)
        .filter(
            Run.vertical_id == vertical_id,
            Run.model_name == model_name,
            Run.answers.any(),
        )
        .order_by(Run.run_time.desc())
        .all()
    )

    if not runs:
        runs = (
            db.query(Run)
            .filter(Run.vertical_id == vertical_id, Run.model_name == model_name)
            .order_by(Run.run_time.desc())
            .all()
        )

    return runs, model_name


def _get_latest_run(db: Session, vertical_id: int, model_name: str) -> Run | None:
    latest_run = (
        db.query(Run)
        .filter(
            Run.vertical_id == vertical_id,
            Run.model_name == model_name,
            Run.answers.any(),
        )
        .order_by(Run.run_time.desc())
        .first()
    )

    if not latest_run:
        latest_run = (
            db.query(Run)
            .filter(
                Run.vertical_id == vertical_id,
                Run.model_name == model_name,
            )
            .order_by(Run.run_time.desc())
            .first()
        )

    return latest_run


def _brand_groups(db: Session, vertical_id: int) -> tuple[dict[int, str], dict[str, list[Brand]]]:
    brands = db.query(Brand).filter(Brand.vertical_id == vertical_id).all()
    user_exact, user_norm = build_user_brand_variant_maps(db, vertical_id)
    canon, alias, norm = build_brand_canonical_maps(db, vertical_id)
    id_to_key = _brand_id_to_key(brands, user_exact, user_norm, canon, alias, norm)
    return id_to_key, _group_by_key(brands, id_to_key)


def _product_groups(db: Session, vertical_id: int) -> tuple[dict[int, str], dict[str, list[Product]]]:
    products = db.query(Product).filter(Product.vertical_id == vertical_id).all()
    canon, alias, norm = build_product_canonical_maps(db, vertical_id)
    id_to_key = _product_id_to_key(products, canon, alias, norm)
    return id_to_key, _group_by_key(products, id_to_key)


def _brand_id_to_key(
    brands: list[Brand],
    user_exact: dict[str, str],
    user_norm: dict[str, str],
    canon: dict[str, str],
    alias: dict[str, str],
    norm: dict[str, str],
) -> dict[int, str]:
    id_to_key = {b.id: _brand_key(b, user_exact, user_norm, canon, alias, norm) for b in brands}
    return _fill_unresolved_brand_keys(brands, id_to_key)


def _product_id_to_key(
    products: list[Product],
    canon: dict[str, str],
    alias: dict[str, str],
    norm: dict[str, str],
) -> dict[int, str]:
    id_to_key = {p.id: _product_key(p, canon, alias, norm) for p in products}
    return _fill_unresolved_product_keys(products, id_to_key)


def _brand_key(
    brand: Brand, user_exact: dict[str, str], user_norm: dict[str, str], canon: dict[str, str], alias: dict[str, str], norm: dict[str, str]
) -> str | None:
    if brand.is_user_input:
        return brand.display_name
    return resolve_brand_key(brand.display_name, user_exact, user_norm, canon, alias, norm)


def _product_key(product: Product, canon: dict[str, str], alias: dict[str, str], norm: dict[str, str]) -> str | None:
    if product.is_user_input:
        return product.display_name
    return resolve_canonical_key(product.display_name, canon, alias, norm)


def _group_by_key(items: list, id_to_key: dict[int, str]) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for item in items:
        grouped.setdefault(id_to_key[item.id], []).append(item)
    return grouped


def _fill_unresolved_brand_keys(brands: list[Brand], id_to_key: dict[int, str | None]) -> dict[int, str]:
    unresolved = _unresolved_by_norm(brands, id_to_key)
    resolved = {bid: key for bid, key in id_to_key.items() if key}
    for group in unresolved.values():
        rep = choose_brand_rep(group)
        resolved.update({b.id: rep.display_name for b in group})
    return resolved


def _fill_unresolved_product_keys(products: list[Product], id_to_key: dict[int, str | None]) -> dict[int, str]:
    unresolved = _unresolved_by_norm(products, id_to_key)
    resolved = {pid: key for pid, key in id_to_key.items() if key}
    for group in unresolved.values():
        rep = choose_product_rep(group)
        resolved.update({p.id: rep.display_name for p in group})
    return resolved


def _unresolved_by_norm(items: list, id_to_key: dict[int, str | None]) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for item in items:
        if id_to_key[item.id]:
            continue
        grouped.setdefault(normalize_entity_key(item.display_name), []).append(item)
    return grouped


def _brand_answer_metrics(mentions: list[BrandMention], id_to_key: dict[int, str]) -> list[AnswerMetrics]:
    return [_to_answer_metric(m, id_to_key.get(m.brand_id)) for m in mentions if m.mentioned]


def _product_answer_metrics(mentions: list[ProductMention], id_to_key: dict[int, str]) -> list[AnswerMetrics]:
    return [_to_answer_metric(m, id_to_key.get(m.product_id)) for m in mentions if m.mentioned]


def _to_answer_metric(mention, key: str | None) -> AnswerMetrics:
    return AnswerMetrics(prompt_id=mention.llm_answer.prompt_id, brand=key or "", rank=mention.rank, sentiment=mention.sentiment.value)


def _collapse_answer_metrics(metrics: list[AnswerMetrics]) -> list[AnswerMetrics]:
    grouped: dict[tuple[int, str], list[AnswerMetrics]] = {}
    for m in metrics:
        grouped.setdefault((m.prompt_id, m.brand), []).append(m)
    return [_collapsed(k[0], k[1], v) for k, v in grouped.items() if k[1]]


def _collapsed(prompt_id: int, brand: str, items: list[AnswerMetrics]) -> AnswerMetrics:
    ranks = [m.rank for m in items]
    sentiments = [m.sentiment for m in items]
    return AnswerMetrics(prompt_id=prompt_id, brand=brand, rank=_best_rank(ranks), sentiment=_best_sentiment(sentiments))


def _best_rank(ranks: list[int | None]) -> int | None:
    present = [r for r in ranks if r is not None]
    return min(present) if present else None


def _best_sentiment(sentiments: list[str]) -> str:
    if "positive" in sentiments:
        return "positive"
    if "neutral" in sentiments:
        return "neutral"
    return "negative"


def _brand_keys(answer_metrics: list[AnswerMetrics], groups: dict[str, list[Brand]]) -> list[str]:
    mentioned = {m.brand for m in answer_metrics}
    user = {k for k, bs in groups.items() if any(b.is_user_input for b in bs)}
    return sorted(mentioned | user)


def _product_keys(answer_metrics: list[AnswerMetrics], groups: dict[str, list[Product]]) -> list[str]:
    mentioned = {m.brand for m in answer_metrics}
    user = {k for k, ps in groups.items() if any(p.is_user_input for p in ps)}
    return sorted(mentioned | user)


@router.get("/daily")
async def get_daily_metrics(
    vertical_id: int = Query(..., description="Vertical ID"),
    brand_id: int = Query(..., description="Brand ID"),
    model_name: str = Query(..., description="Model name"),
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    db: Session = Depends(get_db),
):
    """
    Get daily metrics for a specific brand over time.

    Args:
        vertical_id: Vertical ID
        brand_id: Brand ID
        model_name: Model name
        start_date: Start date (optional)
        end_date: End date (optional)
        db: Database session

    Returns:
        Daily metrics time series
    """
    get_vertical_or_raise(db, vertical_id)
    validate_brand_belongs_to_vertical(db, brand_id, vertical_id)
    validate_date_range(start_date, end_date)

    query = db.query(DailyMetrics).filter(
        DailyMetrics.vertical_id == vertical_id,
        DailyMetrics.brand_id == brand_id,
        DailyMetrics.model_name == model_name,
    )

    if start_date:
        query = query.filter(DailyMetrics.date >= start_date)
    if end_date:
        query = query.filter(DailyMetrics.date <= end_date)

    metrics = query.order_by(DailyMetrics.date).all()

    return {
        "vertical_id": vertical_id,
        "brand_id": brand_id,
        "model_name": model_name,
        "data": [
            {
                "date": m.date,
                "mention_rate": m.mention_rate,
                "share_of_voice": m.share_of_voice,
                "top_spot_share": m.top_spot_share,
                "sentiment_index": m.sentiment_index,
                "dragon_lens_visibility": m.dragon_lens_visibility,
            }
            for m in metrics
        ],
    }


@router.get("/run/{run_id}", response_model=AllRunMetricsResponse)
async def get_run_metrics(
    run_id: int,
    db: Session = Depends(get_db),
) -> AllRunMetricsResponse:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    vertical = db.query(Vertical).filter(Vertical.id == run.vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {run.vertical_id} not found")

    run_metrics = db.query(RunMetrics).filter(RunMetrics.run_id == run_id).all()

    metrics_responses = []
    for metric in run_metrics:
        brand = db.query(Brand).filter(Brand.id == metric.brand_id).first()
        if not brand:
            continue

        metrics_responses.append(
            RunMetricsResponse(
                brand_id=metric.brand_id,
                brand_name=format_entity_label(brand.original_name, brand.translated_name),
                is_user_input=brand.is_user_input,
                top_spot_share=metric.top_spot_share,
                sentiment_index=metric.sentiment_index,
                mention_rate=metric.mention_rate,
                share_of_voice=metric.share_of_voice,
                dragon_lens_visibility=metric.dragon_lens_visibility,
            )
        )

    return AllRunMetricsResponse(
        run_id=run.id,
        vertical_id=run.vertical_id,
        vertical_name=vertical.name,
        provider=run.provider,
        model_name=run.model_name,
        run_time=run.run_time,
        metrics=metrics_responses,
    )


@router.get("/run/{run_id}/products", response_model=AllRunProductMetricsResponse)
async def get_run_product_metrics(
    run_id: int,
    db: Session = Depends(get_db),
) -> AllRunProductMetricsResponse:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    vertical = get_vertical_or_raise(db, run.vertical_id)
    rows = db.query(RunProductMetrics).filter(RunProductMetrics.run_id == run_id).all()
    products = [_run_product_metric(db, r) for r in rows]
    return AllRunProductMetricsResponse(
        run_id=run.id,
        vertical_id=run.vertical_id,
        vertical_name=vertical.name,
        provider=run.provider,
        model_name=run.model_name,
        run_time=run.run_time,
        products=[p for p in products if p],
    )


def _run_product_metric(db: Session, row: RunProductMetrics) -> ProductMetrics | None:
    product = db.query(Product).filter(Product.id == row.product_id).first()
    if not product:
        return None
    brand_name = ""
    if product.brand:
        brand_name = format_entity_label(product.brand.original_name, product.brand.translated_name)
    return ProductMetrics(
        product_id=product.id,
        product_name=format_entity_label(product.original_name, product.translated_name),
        brand_id=product.brand_id,
        brand_name=brand_name,
        mention_rate=row.mention_rate,
        share_of_voice=row.share_of_voice,
        top_spot_share=row.top_spot_share,
        sentiment_index=row.sentiment_index,
        dragon_lens_visibility=row.dragon_lens_visibility,
    )


@router.get("/run/{run_id}/comparison", response_model=RunComparisonMetricsResponse)
async def get_run_comparison_metrics(
    run_id: int,
    entity_type: str = Query("all", pattern="^(all|brand|product)$"),
    include_snippets: bool = Query(False),
    limit_entities: int = Query(50, ge=1, le=500),
    limit_snippets: int = Query(3, ge=0, le=50),
    db: Session = Depends(get_db),
) -> RunComparisonMetricsResponse:
    """
    Get comparison sentiment results for a run.

    Comparison prompts are executed after the main run completes and are never used for brand/product extraction.
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    config = db.query(RunComparisonConfig).filter(RunComparisonConfig.run_id == run_id).first()
    if not config or not config.enabled:
        raise HTTPException(status_code=404, detail=f"Comparison results not available for run {run_id}")
    if config.status != ComparisonRunStatus.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Comparison results not ready (status={config.status.value})")
    vertical = get_vertical_or_raise(db, run.vertical_id)
    primary = db.query(Brand).filter(Brand.id == config.primary_brand_id).first()
    messages = _comparison_messages(db, run_id)
    brands = [] if entity_type == "product" else _comparison_summaries(db, run_id, EntityType.BRAND, include_snippets, limit_entities, limit_snippets)
    products = [] if entity_type == "brand" else _comparison_summaries(db, run_id, EntityType.PRODUCT, include_snippets, limit_entities, limit_snippets)
    return RunComparisonMetricsResponse(
        run_id=run.id,
        vertical_id=run.vertical_id,
        vertical_name=vertical.name,
        provider=run.provider,
        model_name=run.model_name,
        primary_brand_id=config.primary_brand_id,
        primary_brand_name=format_entity_label(primary.original_name, primary.translated_name) if primary else "",
        brands=brands,
        products=products,
        messages=messages,
    )


def _comparison_messages(db: Session, run_id: int) -> list[RunComparisonMessage]:
    rows = db.query(ComparisonRunEvent).filter(ComparisonRunEvent.run_id == run_id).order_by(ComparisonRunEvent.created_at).all()
    return [RunComparisonMessage(level=r.level, code=r.code, message=r.message) for r in rows]


def _comparison_summaries(
    db: Session,
    run_id: int,
    entity_type: EntityType,
    include_snippets: bool,
    limit_entities: int,
    limit_snippets: int,
) -> list[ComparisonEntitySentimentSummary]:
    rows = (
        db.query(
            ComparisonSentimentObservation.entity_id,
            ComparisonSentimentObservation.entity_role,
            ComparisonSentimentObservation.sentiment,
            ComparisonSentimentObservation.snippet_zh,
            ComparisonSentimentObservation.snippet_en,
            ComparisonSentimentObservation.aspect,
            ComparisonSentimentObservation.created_at,
        )
        .filter(ComparisonSentimentObservation.run_id == run_id, ComparisonSentimentObservation.entity_type == entity_type)
        .order_by(ComparisonSentimentObservation.created_at.desc())
        .all()
    )
    ids = _limited_entity_ids(rows, limit_entities)
    name_map = _entity_names(db, entity_type, ids)
    return [_entity_summary(entity_type, i, name_map.get(i, ""), rows, include_snippets, limit_snippets) for i in ids]


def _limited_entity_ids(rows: list, limit_entities: int) -> list[int]:
    seen: set[int] = set()
    ids: list[int] = []
    for r in rows:
        entity_id = int(r[0])
        if entity_id in seen:
            continue
        seen.add(entity_id)
        ids.append(entity_id)
        if len(ids) >= int(limit_entities):
            break
    return ids


def _entity_names(db: Session, entity_type: EntityType, ids: list[int]) -> dict[int, str]:
    if not ids:
        return {}
    if entity_type == EntityType.BRAND:
        brands = db.query(Brand).filter(Brand.id.in_(ids)).all()
        return {b.id: format_entity_label(b.original_name, b.translated_name) for b in brands}
    products = db.query(Product).filter(Product.id.in_(ids)).all()
    return {p.id: format_entity_label(p.original_name, p.translated_name) for p in products}


def _entity_summary(
    entity_type: EntityType,
    entity_id: int,
    entity_name: str,
    rows: list,
    include_snippets: bool,
    limit_snippets: int,
) -> ComparisonEntitySentimentSummary:
    pos, neu, neg = _sentiment_counts(rows, entity_id)
    snippets = [] if not include_snippets else _snippets(rows, entity_id, int(limit_snippets))
    role = _entity_role(rows, entity_id)
    total = max(0, pos + neu + neg)
    sentiment_index = float(pos) / float(total) if total else 0.0
    return ComparisonEntitySentimentSummary(
        entity_type=entity_type.value,
        entity_id=entity_id,
        entity_name=entity_name,
        entity_role=role,
        positive_count=pos,
        neutral_count=neu,
        negative_count=neg,
        sentiment_index=sentiment_index,
        snippets=snippets,
    )


def _sentiment_counts(rows: list, entity_id: int) -> tuple[int, int, int]:
    pos = neu = neg = 0
    for r in rows:
        if int(r[0]) != int(entity_id):
            continue
        s = r[2]
        if s == Sentiment.POSITIVE:
            pos += 1
        elif s == Sentiment.NEUTRAL:
            neu += 1
        else:
            neg += 1
    return pos, neu, neg


def _entity_role(rows: list, entity_id: int) -> str:
    for r in rows:
        if int(r[0]) == int(entity_id) and r[1]:
            return r[1].value
    return "competitor"


def _snippets(rows: list, entity_id: int, limit_snippets: int) -> list[ComparisonEvidenceSnippet]:
    out: list[ComparisonEvidenceSnippet] = []
    for r in rows:
        if int(r[0]) != int(entity_id):
            continue
        out.append(ComparisonEvidenceSnippet(snippet_zh=r[3], snippet_en=r[4], sentiment=r[2].value, aspect=r[5]))
        if len(out) >= limit_snippets:
            break
    return out


def _aspect_en(aspect_zh: str) -> str:
    mapping = {
        "油耗": "Fuel efficiency",
        "空间": "Space",
        "舒适性": "Comfort",
        "安全性": "Safety",
        "性价比": "Value for money",
        "可靠性": "Reliability",
        "售后": "After-sales service",
        "做工用料": "Build quality and materials",
        "动力表现": "Performance",
        "保值率": "Resale value",
    }
    return mapping.get((aspect_zh or "").strip(), (aspect_zh or "").strip())


def _outcome_for_obs(rows: list[ComparisonSentimentObservation]) -> str:
    from services.comparison_prompts.outcomes import outcome_for_role_sentiments

    pairs = [(r.entity_role, r.sentiment) for r in rows if r.entity_role and r.sentiment]
    return outcome_for_role_sentiments(pairs)


def _characteristic(prompt: ComparisonPrompt) -> str:
    if prompt.aspects and isinstance(prompt.aspects, list) and prompt.aspects:
        return str(prompt.aspects[0] or "").strip()
    return ""


def _fallback_product_name(product: Product | None) -> str:
    if not product:
        return ""
    return format_entity_label(product.original_name, product.translated_name)


@router.get("/run/{run_id}/comparison/summary", response_model=RunComparisonSummaryResponse)
async def get_run_comparison_summary(
    run_id: int,
    include_prompt_details: bool = Query(False),
    limit_prompts: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> RunComparisonSummaryResponse:
    """
    Get winner/loser summary for comparison prompts grouped by characteristic.
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    config = db.query(RunComparisonConfig).filter(RunComparisonConfig.run_id == run_id).first()
    if not config or not config.enabled:
        raise HTTPException(status_code=404, detail=f"Comparison results not available for run {run_id}")
    if config.status != ComparisonRunStatus.COMPLETED:
        raise HTTPException(status_code=409, detail=f"Comparison results not ready (status={config.status.value})")
    vertical = get_vertical_or_raise(db, run.vertical_id)
    primary = db.query(Brand).filter(Brand.id == config.primary_brand_id).first()
    messages = _comparison_messages(db, run_id)
    brands = _comparison_summaries(db, run_id, EntityType.BRAND, False, 500, 0)
    products = _comparison_summaries(db, run_id, EntityType.PRODUCT, False, 500, 0)
    prompts, characteristics = _summary_prompts_and_characteristics(db, run_id, int(limit_prompts), bool(include_prompt_details))
    return RunComparisonSummaryResponse(
        run_id=run.id,
        vertical_id=run.vertical_id,
        vertical_name=vertical.name,
        provider=run.provider,
        model_name=run.model_name,
        primary_brand_id=config.primary_brand_id,
        primary_brand_name=format_entity_label(primary.original_name, primary.translated_name) if primary else "",
        brands=brands,
        products=products,
        characteristics=characteristics,
        prompts=prompts,
        messages=messages,
    )


def _summary_prompts_and_characteristics(
    db: Session,
    run_id: int,
    limit_prompts: int,
    include_prompt_details: bool,
) -> tuple[list[ComparisonPromptOutcomeDetail], list[ComparisonCharacteristicSummary]]:
    prompts = db.query(ComparisonPrompt).filter(ComparisonPrompt.run_id == run_id).order_by(ComparisonPrompt.id).limit(limit_prompts).all()
    answers = db.query(ComparisonAnswer).filter(ComparisonAnswer.run_id == run_id).all()
    answer_by_prompt = {int(a.comparison_prompt_id): a for a in answers}
    prod_ids = _prompt_product_ids(prompts)
    products = db.query(Product).filter(Product.id.in_(prod_ids)).all() if prod_ids else []
    prod_map = {int(p.id): p for p in products}
    details = [] if not include_prompt_details else [_prompt_detail(db, p, answer_by_prompt.get(int(p.id)), prod_map) for p in prompts]
    outcomes = [_prompt_outcome(db, p, answer_by_prompt.get(int(p.id))) for p in prompts]
    return details, _characteristic_summaries(outcomes)


def _prompt_product_ids(prompts: list[ComparisonPrompt]) -> list[int]:
    ids: set[int] = set()
    for p in prompts:
        for pid in [p.primary_product_id, p.competitor_product_id]:
            if pid:
                ids.add(int(pid))
    return list(ids)


def _prompt_outcome(db: Session, prompt: ComparisonPrompt, answer: ComparisonAnswer | None) -> dict:
    aspect_zh = _characteristic(prompt)
    aspect_en = _aspect_en(aspect_zh)
    obs = [] if not answer else db.query(ComparisonSentimentObservation).filter(
        ComparisonSentimentObservation.comparison_answer_id == answer.id,
        ComparisonSentimentObservation.entity_type == EntityType.PRODUCT,
    ).all()
    outcome = _outcome_for_obs(obs)
    return {"characteristic_zh": aspect_zh, "characteristic_en": aspect_en, "winner_role": outcome}


def _prompt_detail(
    db: Session,
    prompt: ComparisonPrompt,
    answer: ComparisonAnswer | None,
    prod_map: dict[int, Product],
) -> ComparisonPromptOutcomeDetail:
    aspect_zh = _characteristic(prompt)
    aspect_en = _aspect_en(aspect_zh)
    primary_p = prod_map.get(int(prompt.primary_product_id)) if prompt.primary_product_id else None
    competitor_p = prod_map.get(int(prompt.competitor_product_id)) if prompt.competitor_product_id else None
    obs = [] if not answer else db.query(ComparisonSentimentObservation).filter(
        ComparisonSentimentObservation.comparison_answer_id == answer.id,
        ComparisonSentimentObservation.entity_type == EntityType.PRODUCT,
    ).all()
    winner_role = _outcome_for_obs(obs)
    winner_id, loser_id = _winner_loser_ids(prompt, winner_role)
    return ComparisonPromptOutcomeDetail(
        prompt_id=int(prompt.id),
        characteristic_zh=aspect_zh,
        characteristic_en=aspect_en,
        prompt_zh=prompt.text_zh or "",
        prompt_en=prompt.text_en,
        answer_zh=answer.raw_answer_zh if answer else None,
        answer_en=answer.raw_answer_en if answer else None,
        primary_product_id=int(prompt.primary_product_id) if prompt.primary_product_id else None,
        primary_product_name=_fallback_product_name(primary_p),
        competitor_product_id=int(prompt.competitor_product_id) if prompt.competitor_product_id else None,
        competitor_product_name=_fallback_product_name(competitor_p),
        winner_role=winner_role,
        winner_product_id=winner_id,
        winner_product_name=_fallback_product_name(prod_map.get(int(winner_id))) if winner_id else "",
        loser_product_id=loser_id,
        loser_product_name=_fallback_product_name(prod_map.get(int(loser_id))) if loser_id else "",
    )


def _winner_loser_ids(prompt: ComparisonPrompt, winner_role: str) -> tuple[int | None, int | None]:
    primary = int(prompt.primary_product_id) if prompt.primary_product_id else None
    competitor = int(prompt.competitor_product_id) if prompt.competitor_product_id else None
    if winner_role == "primary":
        return primary, competitor
    if winner_role == "competitor":
        return competitor, primary
    return None, None


def _characteristic_summaries(outcomes: list[dict]) -> list[ComparisonCharacteristicSummary]:
    out: dict[str, dict] = {}
    for o in outcomes:
        key = str(o.get("characteristic_zh") or "").strip()
        en = str(o.get("characteristic_en") or "").strip()
        bucket = out.get(key) or {"en": en, "total": 0, "primary": 0, "competitor": 0, "tie": 0, "unknown": 0}
        bucket["total"] += 1
        winner = o.get("winner_role")
        if winner == "primary":
            bucket["primary"] += 1
        elif winner == "competitor":
            bucket["competitor"] += 1
        elif winner == "tie":
            bucket["tie"] += 1
        else:
            bucket["unknown"] += 1
        out[key] = bucket
    return [ComparisonCharacteristicSummary(
        characteristic_zh=k,
        characteristic_en=v["en"] or k,
        total_prompts=v["total"],
        primary_wins=v["primary"],
        competitor_wins=v["competitor"],
        ties=v["tie"],
        unknown=v["unknown"],
    ) for k, v in out.items() if k]


@router.get("/run/{run_id}/features")
async def get_run_feature_metrics(
    run_id: int,
    entity_type: str = Query("brand", pattern="^(brand|product)$"),
    entity_ids: Optional[str] = Query(None, description="Comma-separated entity IDs"),
    top_features: int = Query(6, ge=1, le=20),
    db: Session = Depends(get_db),
):
    from models.schemas import (
        EntityFeatureDataSchema,
        FeatureScoreSchema,
        RunFeatureMetricsResponse,
    )
    from services.feature_metrics_service import get_spider_chart_data

    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    entity_type_enum = EntityType.BRAND if entity_type == "brand" else EntityType.PRODUCT

    if entity_ids:
        ids = [int(i.strip()) for i in entity_ids.split(",") if i.strip().isdigit()]
    else:
        if entity_type_enum == EntityType.BRAND:
            brands = db.query(Brand).filter(Brand.vertical_id == run.vertical_id).all()
            ids = [b.id for b in brands]
        else:
            products = db.query(Product).filter(Product.vertical_id == run.vertical_id).all()
            ids = [p.id for p in products]

    if not ids:
        return RunFeatureMetricsResponse(
            run_id=run_id,
            vertical_id=run.vertical_id,
            vertical_name="",
            top_features=[],
            entities=[],
        )

    chart_data = get_spider_chart_data(db, run_id, ids, entity_type_enum, top_features)

    if not chart_data:
        return RunFeatureMetricsResponse(
            run_id=run_id,
            vertical_id=run.vertical_id,
            vertical_name="",
            top_features=[],
            entities=[],
        )

    entities_response = []
    for entity in chart_data.entities:
        features_response = [
            FeatureScoreSchema(
                feature_id=f.feature_id,
                feature_name_zh=f.feature_name_zh,
                feature_name_en=f.feature_name_en,
                frequency=f.frequency,
                positive_count=f.positive_count,
                neutral_count=f.neutral_count,
                negative_count=f.negative_count,
                combined_score=f.combined_score,
            )
            for f in entity.features
        ]
        entities_response.append(
            EntityFeatureDataSchema(
                entity_id=entity.entity_id,
                entity_name=entity.entity_name,
                entity_type=entity.entity_type,
                features=features_response,
            )
        )

    return RunFeatureMetricsResponse(
        run_id=chart_data.run_id,
        vertical_id=chart_data.vertical_id,
        vertical_name=chart_data.vertical_name,
        top_features=chart_data.top_features,
        entities=entities_response,
    )
