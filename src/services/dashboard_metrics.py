from datetime import datetime

from sqlalchemy.orm import Session

from metrics.metrics import AnswerMetrics, visibility_metrics
from models import (
    Brand,
    BrandMention,
    LLMAnswer,
    Product,
    ProductMention,
    Prompt,
    Run,
    RunMetrics,
    RunProductMetrics,
    Vertical,
)
from models.schemas import (
    AllRunMetricsResponse,
    AllRunProductMetricsResponse,
    BrandMetrics,
    MetricsResponse,
    ProductMetrics,
    ProductMetricsResponse,
    RunMetricsResponse,
    RunResponse,
)
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
from services.translater import format_entity_label


def get_latest_brand_metrics(
    db: Session,
    vertical_id: int,
    model_name: str,
) -> MetricsResponse:
    vertical = _vertical_or_raise(db, vertical_id)
    brand_id_to_key, brand_groups = _brand_groups(db, vertical_id)
    runs, display_model = _runs_for_model(db, vertical_id, model_name)
    run_ids = [run.id for run in runs]
    latest_run_time = max(run.run_time for run in runs)
    prompt_ids = _prompt_ids(db, vertical_id)
    mentions = (
        db.query(BrandMention)
        .join(LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id)
        .filter(LLMAnswer.run_id.in_(run_ids))
        .all()
    )
    answer_metrics = _collapse_answer_metrics(
        _brand_answer_metrics(mentions, brand_id_to_key)
    )
    keys = _brand_keys(answer_metrics, brand_groups)
    brand_metrics = [
        _brand_metric(prompt_ids, answer_metrics, key, keys, brand_groups)
        for key in keys
    ]
    return MetricsResponse(
        vertical_id=vertical_id,
        vertical_name=vertical.name,
        model_name=display_model,
        date=latest_run_time,
        brands=brand_metrics,
    )


def get_latest_product_metrics(
    db: Session,
    vertical_id: int,
    model_name: str,
) -> ProductMetricsResponse:
    vertical = _vertical_or_raise(db, vertical_id)
    product_id_to_key, product_groups = _product_groups(db, vertical_id)
    runs, display_model = _runs_for_model(db, vertical_id, model_name)
    run_ids = [run.id for run in runs]
    latest_run_time = max(run.run_time for run in runs)
    prompt_ids = _prompt_ids(db, vertical_id)
    mentions = (
        db.query(ProductMention)
        .join(LLMAnswer, LLMAnswer.id == ProductMention.llm_answer_id)
        .filter(LLMAnswer.run_id.in_(run_ids))
        .all()
    )
    answer_metrics = _collapse_answer_metrics(
        _product_answer_metrics(mentions, product_id_to_key)
    )
    keys = _product_keys(answer_metrics, product_groups)
    product_metrics = [
        _product_metric(prompt_ids, answer_metrics, key, keys, product_groups)
        for key in keys
    ]
    return ProductMetricsResponse(
        vertical_id=vertical_id,
        vertical_name=vertical.name,
        model_name=display_model,
        date=latest_run_time,
        products=product_metrics,
    )


def get_latest_completed_run(
    db: Session,
    vertical_id: int,
    model_name: str,
) -> RunResponse | None:
    run = (
        db.query(Run)
        .filter(
            Run.vertical_id == vertical_id,
            Run.model_name == model_name,
            Run.status == "completed",
        )
        .order_by(Run.run_time.desc(), Run.id.desc())
        .first()
    )
    if not run:
        return None
    return RunResponse.model_validate(run)


def get_run_brand_metrics(db: Session, run_id: int) -> AllRunMetricsResponse:
    run = _run_or_raise(db, run_id)
    vertical = _vertical_or_raise(db, run.vertical_id)
    rows = db.query(RunMetrics).filter(RunMetrics.run_id == run_id).all()
    metrics = [_run_brand_metric(db, row) for row in rows]
    return AllRunMetricsResponse(
        run_id=run.id,
        vertical_id=run.vertical_id,
        vertical_name=vertical.name,
        provider=run.provider,
        model_name=run.model_name,
        run_time=run.run_time,
        metrics=[metric for metric in metrics if metric],
    )


def get_run_product_metrics(db: Session, run_id: int) -> AllRunProductMetricsResponse:
    run = _run_or_raise(db, run_id)
    vertical = _vertical_or_raise(db, run.vertical_id)
    rows = db.query(RunProductMetrics).filter(RunProductMetrics.run_id == run_id).all()
    products = [_run_product_metric(db, row) for row in rows]
    return AllRunProductMetricsResponse(
        run_id=run.id,
        vertical_id=run.vertical_id,
        vertical_name=vertical.name,
        provider=run.provider,
        model_name=run.model_name,
        run_time=run.run_time,
        products=[product for product in products if product],
    )


def list_available_models(db: Session, vertical_id: int) -> list[str]:
    _vertical_or_raise(db, vertical_id)
    models = (
        db.query(Run.model_name)
        .filter(Run.vertical_id == vertical_id, Run.status == "completed")
        .distinct()
        .all()
    )
    return sorted(model_name for model_name, in models)


def _vertical_or_raise(db: Session, vertical_id: int) -> Vertical:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise ValueError(f"Vertical {vertical_id} not found")
    return vertical


def _run_or_raise(db: Session, run_id: int) -> Run:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")
    return run


def _runs_for_model(
    db: Session,
    vertical_id: int,
    model_name: str,
) -> tuple[list[Run], str]:
    runs = _all_model_runs(db, vertical_id) if model_name == "all" else _single_model_runs(
        db,
        vertical_id,
        model_name,
    )
    if not runs:
        detail = f"No runs found for vertical {vertical_id}"
        if model_name != "all":
            detail += f" and model {model_name}"
        raise ValueError(detail)
    return runs, "All Models" if model_name == "all" else model_name


def _all_model_runs(db: Session, vertical_id: int) -> list[Run]:
    runs = (
        db.query(Run)
        .filter(Run.vertical_id == vertical_id, Run.answers.any())
        .order_by(Run.run_time.desc())
        .all()
    )
    if runs:
        return runs
    return (
        db.query(Run)
        .filter(Run.vertical_id == vertical_id)
        .order_by(Run.run_time.desc())
        .all()
    )


def _single_model_runs(db: Session, vertical_id: int, model_name: str) -> list[Run]:
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
    if runs:
        return runs
    return (
        db.query(Run)
        .filter(Run.vertical_id == vertical_id, Run.model_name == model_name)
        .order_by(Run.run_time.desc())
        .all()
    )


def _prompt_ids(db: Session, vertical_id: int) -> list[int]:
    prompts = db.query(Prompt).filter(Prompt.vertical_id == vertical_id).all()
    return [prompt.id for prompt in prompts]


def _brand_groups(
    db: Session,
    vertical_id: int,
) -> tuple[dict[int, str], dict[str, list[Brand]]]:
    brands = db.query(Brand).filter(Brand.vertical_id == vertical_id).all()
    user_exact, user_norm = build_user_brand_variant_maps(db, vertical_id)
    canon, alias, norm = build_brand_canonical_maps(db, vertical_id)
    id_to_key = {
        brand.id: _brand_key(brand, user_exact, user_norm, canon, alias, norm)
        for brand in brands
    }
    return _fill_unresolved_brand_keys(brands, id_to_key), _group_by_key(
        brands,
        _fill_unresolved_brand_keys(brands, id_to_key),
    )


def _product_groups(
    db: Session,
    vertical_id: int,
) -> tuple[dict[int, str], dict[str, list[Product]]]:
    products = db.query(Product).filter(Product.vertical_id == vertical_id).all()
    canon, alias, norm = build_product_canonical_maps(db, vertical_id)
    id_to_key = {
        product.id: _product_key(product, canon, alias, norm)
        for product in products
    }
    return _fill_unresolved_product_keys(products, id_to_key), _group_by_key(
        products,
        _fill_unresolved_product_keys(products, id_to_key),
    )


def _brand_key(
    brand: Brand,
    user_exact: dict[str, str],
    user_norm: dict[str, str],
    canon: dict[str, str],
    alias: dict[str, str],
    norm: dict[str, str],
) -> str | None:
    if brand.is_user_input:
        return brand.display_name
    return resolve_brand_key(brand.display_name, user_exact, user_norm, canon, alias, norm)


def _product_key(
    product: Product,
    canon: dict[str, str],
    alias: dict[str, str],
    norm: dict[str, str],
) -> str | None:
    if product.is_user_input:
        return product.display_name
    return resolve_canonical_key(product.display_name, canon, alias, norm)


def _fill_unresolved_brand_keys(
    brands: list[Brand],
    id_to_key: dict[int, str | None],
) -> dict[int, str]:
    unresolved = _unresolved_by_norm(brands, id_to_key)
    resolved = {brand_id: key for brand_id, key in id_to_key.items() if key}
    for group in unresolved.values():
        representative = choose_brand_rep(group)
        resolved.update({brand.id: representative.display_name for brand in group})
    return resolved


def _fill_unresolved_product_keys(
    products: list[Product],
    id_to_key: dict[int, str | None],
) -> dict[int, str]:
    unresolved = _unresolved_by_norm(products, id_to_key)
    resolved = {product_id: key for product_id, key in id_to_key.items() if key}
    for group in unresolved.values():
        representative = choose_product_rep(group)
        resolved.update(
            {product.id: representative.display_name for product in group}
        )
    return resolved


def _unresolved_by_norm(
    items: list[Brand] | list[Product],
    id_to_key: dict[int, str | None],
) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for item in items:
        if id_to_key[item.id]:
            continue
        grouped.setdefault(normalize_entity_key(item.display_name), []).append(item)
    return grouped


def _group_by_key(items: list, id_to_key: dict[int, str]) -> dict[str, list]:
    grouped: dict[str, list] = {}
    for item in items:
        grouped.setdefault(id_to_key[item.id], []).append(item)
    return grouped


def _brand_answer_metrics(
    mentions: list[BrandMention],
    id_to_key: dict[int, str],
) -> list[AnswerMetrics]:
    return [_to_answer_metric(mention, id_to_key.get(mention.brand_id)) for mention in mentions if mention.mentioned]


def _product_answer_metrics(
    mentions: list[ProductMention],
    id_to_key: dict[int, str],
) -> list[AnswerMetrics]:
    return [_to_answer_metric(mention, id_to_key.get(mention.product_id)) for mention in mentions if mention.mentioned]


def _to_answer_metric(mention, key: str | None) -> AnswerMetrics:
    return AnswerMetrics(
        prompt_id=mention.llm_answer.prompt_id,
        brand=key or "",
        rank=mention.rank,
        sentiment=mention.sentiment.value,
    )


def _collapse_answer_metrics(metrics: list[AnswerMetrics]) -> list[AnswerMetrics]:
    grouped: dict[tuple[int, str], list[AnswerMetrics]] = {}
    for metric in metrics:
        grouped.setdefault((metric.prompt_id, metric.brand), []).append(metric)
    return [
        _collapsed(prompt_id, brand, items)
        for (prompt_id, brand), items in grouped.items()
        if brand
    ]


def _collapsed(
    prompt_id: int,
    brand: str,
    items: list[AnswerMetrics],
) -> AnswerMetrics:
    ranks = [item.rank for item in items]
    sentiments = [item.sentiment for item in items]
    return AnswerMetrics(
        prompt_id=prompt_id,
        brand=brand,
        rank=_best_rank(ranks),
        sentiment=_best_sentiment(sentiments),
    )


def _best_rank(ranks: list[int | None]) -> int | None:
    present = [rank for rank in ranks if rank is not None]
    return min(present) if present else None


def _best_sentiment(sentiments: list[str]) -> str:
    if "positive" in sentiments:
        return "positive"
    if "neutral" in sentiments:
        return "neutral"
    return "negative"


def _brand_keys(
    answer_metrics: list[AnswerMetrics],
    groups: dict[str, list[Brand]],
) -> list[str]:
    mentioned = {metric.brand for metric in answer_metrics}
    user = {
        key for key, brands in groups.items() if any(brand.is_user_input for brand in brands)
    }
    return sorted(mentioned | user)


def _product_keys(
    answer_metrics: list[AnswerMetrics],
    groups: dict[str, list[Product]],
) -> list[str]:
    mentioned = {metric.brand for metric in answer_metrics}
    user = {
        key
        for key, products in groups.items()
        if any(product.is_user_input for product in products)
    }
    return sorted(mentioned | user)


def _brand_metric(
    prompt_ids: list[int],
    answer_metrics: list[AnswerMetrics],
    key: str,
    all_keys: list[str],
    brand_groups: dict[str, list[Brand]],
) -> BrandMetrics:
    representative = choose_brand_rep(brand_groups[key])
    competitors = [competitor for competitor in all_keys if competitor != key]
    metrics = visibility_metrics(
        prompt_ids=prompt_ids,
        mentions=answer_metrics,
        brand=key,
        competitor_brands=competitors,
    )
    return BrandMetrics(
        brand_id=representative.id,
        brand_name=format_entity_label(
            representative.original_name,
            representative.translated_name,
        ),
        mention_rate=metrics["mention_rate"],
        share_of_voice=metrics["share_of_voice"],
        top_spot_share=metrics["top_spot_share"],
        sentiment_index=metrics["sentiment_index"],
        dragon_lens_visibility=metrics["dragon_lens_visibility"],
    )


def _product_metric(
    prompt_ids: list[int],
    answer_metrics: list[AnswerMetrics],
    key: str,
    all_keys: list[str],
    product_groups: dict[str, list[Product]],
) -> ProductMetrics:
    representative = choose_product_rep(product_groups[key])
    competitors = [competitor for competitor in all_keys if competitor != key]
    metrics = visibility_metrics(
        prompt_ids=prompt_ids,
        mentions=answer_metrics,
        brand=key,
        competitor_brands=competitors,
    )
    brand_name = ""
    if representative.brand:
        brand_name = format_entity_label(
            representative.brand.original_name,
            representative.brand.translated_name,
        )
    return ProductMetrics(
        product_id=representative.id,
        product_name=format_entity_label(
            representative.original_name,
            representative.translated_name,
        ),
        brand_id=representative.brand_id,
        brand_name=brand_name,
        mention_rate=metrics["mention_rate"],
        share_of_voice=metrics["share_of_voice"],
        top_spot_share=metrics["top_spot_share"],
        sentiment_index=metrics["sentiment_index"],
        dragon_lens_visibility=metrics["dragon_lens_visibility"],
    )


def _run_brand_metric(db: Session, row: RunMetrics) -> RunMetricsResponse | None:
    brand = db.query(Brand).filter(Brand.id == row.brand_id).first()
    if not brand:
        return None
    return RunMetricsResponse(
        brand_id=row.brand_id,
        brand_name=format_entity_label(brand.original_name, brand.translated_name),
        is_user_input=brand.is_user_input,
        top_spot_share=row.top_spot_share,
        sentiment_index=row.sentiment_index,
        mention_rate=row.mention_rate,
        share_of_voice=row.share_of_voice,
        dragon_lens_visibility=row.dragon_lens_visibility,
    )


def _run_product_metric(db: Session, row: RunProductMetrics) -> ProductMetrics | None:
    product = db.query(Product).filter(Product.id == row.product_id).first()
    if not product:
        return None
    brand_name = ""
    if product.brand:
        brand_name = format_entity_label(
            product.brand.original_name,
            product.brand.translated_name,
        )
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
