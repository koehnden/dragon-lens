"""API router for metrics retrieval."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from models import (
    Brand,
    BrandMention,
    DailyMetrics,
    LLMAnswer,
    Product,
    ProductMention,
    Prompt,
    Run,
    RunMetrics,
    Vertical,
    get_db,
)
from metrics.metrics import AnswerMetrics, visibility_metrics
from models.schemas import (
    AllRunMetricsResponse,
    BrandMetrics,
    MetricsResponse,
    ProductMetrics,
    ProductMetricsResponse,
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
