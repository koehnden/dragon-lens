"""API router for tracking job management."""

import asyncio
import logging
import os
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload, sessionmaker

from models import (
    Brand,
    BrandMention,
    LLMAnswer,
    Product,
    ProductBrandMapping,
    ProductMention,
    Prompt,
    Run,
    RunComparisonConfig,
    Vertical,
    get_db,
)
from models.knowledge_database import get_knowledge_db_write
from models.db_retry import commit_with_retry, flush_with_retry
from models.domain import PromptLanguage, RunStatus, Sentiment
from models.schemas import (
    BrandMentionResponse,
    DeleteJobsResponse,
    LLMAnswerResponse,
    RunEntitiesResponse,
    RunEntityBrand,
    RunEntityMapping,
    RunEntityProduct,
    RunDetailedResponse,
    RunInspectorPromptExport,
    RunResponse,
    FeedbackCanonicalVertical,
    TrackingJobCreate,
    TrackingJobResponse,
)
from services.feedback_service import save_vertical_alias
from services.translater import format_entity_label
from services.metrics_service import calculate_and_save_metrics
from services.run_inspector_export import build_run_inspector_export

logger = logging.getLogger(__name__)

router = APIRouter()

RUN_TASKS_INLINE = os.getenv("RUN_TASKS_INLINE", "false").lower() == "true"


def _provided_filters(
    id: int | None,
    status: str | None,
    latest: bool | None,
    all: bool | None,
    vertical_name: str | None,
) -> list[str]:
    return [
        name
        for name, value in [
            ("id", id),
            ("status", status),
            ("latest", latest),
            ("all", all),
            ("vertical_name", vertical_name),
        ]
        if value
    ]


@router.post("/jobs", response_model=TrackingJobResponse, status_code=201)
async def create_tracking_job(
    job: TrackingJobCreate,
    db: Session = Depends(get_db),
    knowledge_db: Session = Depends(get_knowledge_db_write),
) -> TrackingJobResponse:
    """
    Create a new tracking job.

    This will:
    1. Create or get the vertical
    2. Create brands and prompts
    3. Create a Run record
    4. Enqueue a Celery task to process the tracking (TODO)

    Args:
        job: Tracking job configuration
        db: Database session

    Returns:
        Tracking job response with run ID
    """
    from sqlalchemy import func as sqla_func

    vertical = db.query(Vertical).filter(Vertical.name == job.vertical_name).first()
    if not vertical:
        vertical = Vertical(
            name=job.vertical_name,
            description=job.vertical_description,
        )
        db.add(vertical)
        flush_with_retry(db)
    canonical = job.canonical_vertical or FeedbackCanonicalVertical(name=vertical.name, is_new=True)
    save_vertical_alias(db, knowledge_db, vertical.id, canonical)

    for brand_data in job.brands:
        existing_brand = (
            db.query(Brand)
            .filter(
                Brand.vertical_id == vertical.id,
                sqla_func.lower(Brand.display_name) == brand_data.display_name.lower(),
            )
            .first()
        )
        if existing_brand:
            continue
        brand = Brand(
            vertical_id=vertical.id,
            display_name=brand_data.display_name,
            original_name=brand_data.display_name,
            translated_name=None,
            aliases=brand_data.aliases,
        )
        db.add(brand)

    run = Run(
        vertical_id=vertical.id,
        provider=job.provider,
        model_name=job.model_name,
        status=RunStatus.PENDING,
        reuse_answers=job.reuse_answers,
        web_search_enabled=job.web_search_enabled,
    )
    db.add(run)
    flush_with_retry(db)

    for prompt_data in job.prompts:
        prompt = Prompt(
            vertical_id=vertical.id,
            run_id=run.id,
            text_en=prompt_data.text_en,
            text_zh=prompt_data.text_zh,
            language_original=PromptLanguage(prompt_data.language_original),
        )
        db.add(prompt)

    commit_with_retry(db)
    db.refresh(run)
    _create_run_comparison_config(db, run.id, vertical.id, job)

    if RUN_TASKS_INLINE:
        engine = db.get_bind()
        asyncio.create_task(_process_run_inline(run.id, vertical.id, engine))
        return TrackingJobResponse(
            run_id=run.id,
            vertical_id=vertical.id,
            provider=job.provider,
            model_name=job.model_name,
            route=run.route.value if run.route else None,
            status=run.status.value,
            message="Tracking job queued for inline processing."
        )

    from workers.tasks import start_run

    enqueue_message = "Tracking job created successfully. Processing will start shortly."
    try:
        start_run.delay(run.id, False)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(
            "Failed to enqueue vertical analysis for run %s: %s", run.id, exc
        )
        run.error_message = str(exc)
        commit_with_retry(db)
        enqueue_message = (
            "Tracking job created, but background processing could not be enqueued. "
            "Please ensure the Celery worker and broker are available."
        )

    return TrackingJobResponse(
        run_id=run.id,
        vertical_id=vertical.id,
        provider=job.provider,
        model_name=job.model_name,
        route=run.route.value if run.route else None,
        status=run.status.value,
        message=enqueue_message,
    )


def _create_run_comparison_config(db: Session, run_id: int, vertical_id: int, job: TrackingJobCreate) -> None:
    primary_brand = _primary_brand_or_none(db, vertical_id, job)
    if not primary_brand:
        return
    config = RunComparisonConfig(
        run_id=run_id,
        vertical_id=vertical_id,
        primary_brand_id=primary_brand.id,
        enabled=True,
        competitor_brands=[],
        target_count=20,
        min_prompts_per_competitor=0,
        autogenerate_missing=True,
    )
    db.add(config)
    commit_with_retry(db)


def _primary_brand_or_none(db: Session, vertical_id: int, job: TrackingJobCreate) -> Brand | None:
    if not job.brands:
        return None
    name = job.brands[0].display_name
    return db.query(Brand).filter(Brand.vertical_id == vertical_id, func.lower(Brand.display_name) == name.lower()).first()


@router.delete("/jobs", response_model=DeleteJobsResponse)
async def delete_tracking_jobs(
    id: int | None = None,
    status: str | None = None,
    latest: bool | None = None,
    all: bool | None = None,
    vertical_name: str | None = None,
    db: Session = Depends(get_db),
) -> DeleteJobsResponse:
    """
    Delete tracking jobs (runs) based on specified criteria.

    Exactly one of the following parameters must be provided:
    - id: Delete a specific job by run ID
    - status: Delete all jobs with a specific status (pending, in_progress, completed, failed)
    - latest: Delete the most recently created job
    - all: Delete all jobs
    - vertical_name: Delete all jobs associated with a specific vertical name

    Returns the vertical IDs of deleted jobs so verticals can be cleaned up afterwards.

    Args:
        id: Specific run ID to delete
        status: Status of runs to delete
        latest: Whether to delete the latest run
        all: Whether to delete all runs
        vertical_name: Name of vertical whose runs should be deleted
        db: Database session

    Returns:
        DeleteJobsResponse with count and affected vertical IDs

    Raises:
        HTTPException: If no parameters provided, multiple parameters provided, or invalid parameters
    """
    provided_filters = _provided_filters(id, status, latest, all, vertical_name)
    if not provided_filters:
        raise HTTPException(
            status_code=400,
            detail="At least one parameter (id, status, latest, all, vertical_name) must be provided"
        )

    if len(provided_filters) > 1:
        provided = ", ".join(provided_filters)
        detail = (
            "Only one filter parameter allow. You passed these "
            f"{provided}! Please stick to one parameter only!"
        )
        raise HTTPException(status_code=400, detail=detail)

    query = db.query(Run)

    filters = []

    if id:
        filters.append(Run.id == id)

    if status:
        try:
            run_status = RunStatus(status)
            filters.append(Run.status == run_status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    if vertical_name:
        vertical = db.query(Vertical).filter(Vertical.name == vertical_name).first()
        if not vertical:
            return DeleteJobsResponse(deleted_count=0, vertical_ids=[])
        filters.append(Run.vertical_id == vertical.id)

    for run_filter in filters:
        query = query.filter(run_filter)

    if latest:
        query = query.order_by(Run.run_time.desc(), Run.id.desc()).limit(1)

    runs_to_delete = query.all()

    vertical_ids = list(set(run.vertical_id for run in runs_to_delete))

    for run in runs_to_delete:
        db.delete(run)

    commit_with_retry(db)

    return DeleteJobsResponse(
        deleted_count=len(runs_to_delete),
        vertical_ids=vertical_ids
    )


@router.get("/runs", response_model=List[RunResponse])
async def list_runs(
    vertical_id: int | None = None,
    provider: str | None = None,
    model_name: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[Run]:
    """
    List tracking runs with optional filters.

    Args:
        vertical_id: Filter by vertical ID
        provider: Filter by LLM provider (qwen, deepseek, kimi)
        model_name: Filter by model name
        skip: Number of records to skip
        limit: Maximum number of records to return
        db: Database session

    Returns:
        List of runs
    """
    query = db.query(Run)

    if vertical_id:
        query = query.filter(Run.vertical_id == vertical_id)
    if provider:
        query = query.filter(Run.provider == provider)
    if model_name:
        query = query.filter(Run.model_name == model_name)

    runs = query.order_by(Run.run_time.desc()).offset(skip).limit(limit).all()
    return runs


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: int,
    db: Session = Depends(get_db),
) -> Run:
    """
    Get details of a specific run.

    Args:
        run_id: Run ID
        db: Database session

    Returns:
        Run details

    Raises:
        HTTPException: If run not found
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    return run


@router.post("/runs/{run_id}/reprocess")
async def reprocess_run(
    run_id: int,
    db: Session = Depends(get_db),
) -> dict:
    """
    Trigger reprocessing of an existing run.

    This will:
    1. Verify the run exists and is not in progress
    2. Enqueue a Celery task to reprocess the run
    3. The task will reuse existing LLM answers and re-run extraction

    Args:
        run_id: Run ID to reprocess
        db: Database session

    Returns:
        Status message

    Raises:
        HTTPException: If run not found or status is in progress
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status == RunStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=409,
            detail=f"Run {run_id} is in progress and cannot be reprocessed",
        )

    if run.status not in {RunStatus.PENDING, RunStatus.COMPLETED, RunStatus.FAILED}:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} cannot be reprocessed (current: {run.status.value})",
        )

    vertical = db.query(Vertical).filter(Vertical.id == run.vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {run.vertical_id} not found")

    if RUN_TASKS_INLINE:
        engine = db.get_bind()
        asyncio.create_task(_process_run_inline(run.id, vertical.id, engine))
        if run.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
            run.status = RunStatus.PENDING
            run.error_message = None
            run.completed_at = None
            commit_with_retry(db)
        return {"message": f"Run {run_id} queued for inline reprocessing", "run_id": run_id}

    from workers.tasks import start_run

    try:
        start_run.delay(run.id, True)
        if run.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
            run.status = RunStatus.PENDING
            run.error_message = None
            run.completed_at = None
            commit_with_retry(db)
        return {"message": f"Run {run_id} queued for reprocessing", "run_id": run_id}
    except Exception as exc:
        logger.warning("Failed to enqueue reprocessing for run %s: %s", run_id, exc)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to enqueue reprocessing: {exc}"
        )


@router.get("/runs/{run_id}/details", response_model=RunDetailedResponse)
async def get_run_details(
    run_id: int,
    db: Session = Depends(get_db),
) -> RunDetailedResponse:
    """
    Get detailed information about a run including answers and mentions.

    Args:
        run_id: Run ID
        db: Database session

    Returns:
        Detailed run information with all answers and brand mentions

    Raises:
        HTTPException: If run not found
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    vertical = db.query(Vertical).filter(Vertical.id == run.vertical_id).first()
    answers_data = []

    for llm_answer in run.answers:
        prompt = db.query(Prompt).filter(Prompt.id == llm_answer.prompt_id).first()
        mentions_data = []

        for mention in llm_answer.mentions:
            brand = db.query(Brand).filter(Brand.id == mention.brand_id).first()
            brand_label = (
                format_entity_label(brand.original_name, brand.translated_name)
                if brand
                else "Unknown"
            )
            mentions_data.append(
                BrandMentionResponse(
                    brand_id=mention.brand_id,
                    brand_name=brand_label,
                    mentioned=mention.mentioned,
                    rank=mention.rank,
                    sentiment=mention.sentiment.value,
                    evidence_snippets=mention.evidence_snippets,
                )
            )

        answers_data.append(
            LLMAnswerResponse(
                id=llm_answer.id,
                prompt_text_zh=prompt.text_zh if prompt else None,
                prompt_text_en=prompt.text_en if prompt else None,
                provider=llm_answer.provider,
                model_name=llm_answer.model_name,
                route=llm_answer.route.value if llm_answer.route else None,
                raw_answer_zh=llm_answer.raw_answer_zh,
                raw_answer_en=llm_answer.raw_answer_en,
                tokens_in=llm_answer.tokens_in,
                tokens_out=llm_answer.tokens_out,
                latency=llm_answer.latency,
                cost_estimate=llm_answer.cost_estimate,
                mentions=mentions_data,
                created_at=llm_answer.created_at,
            )
        )

    return RunDetailedResponse(
        id=run.id,
        vertical_id=run.vertical_id,
        vertical_name=vertical.name if vertical else "Unknown",
        provider=run.provider,
        model_name=run.model_name,
        route=run.route.value if run.route else None,
        status=run.status.value,
        run_time=run.run_time,
        completed_at=run.completed_at,
        error_message=run.error_message,
        answers=answers_data,
    )


@router.get("/runs/{run_id}/inspector-export", response_model=List[RunInspectorPromptExport])
async def export_run_inspector_data(
    run_id: int,
    db: Session = Depends(get_db),
) -> list[dict]:
    """
    Export prompt answers and extracted entities for a run.

    Returns one item per prompt answer with brands, products, snippets, and translations.
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return build_run_inspector_export(db, run_id)


@router.get("/runs/{run_id}/entities", response_model=RunEntitiesResponse)
async def get_run_entities(
    run_id: int,
    db: Session = Depends(get_db),
) -> RunEntitiesResponse:
    """Get extracted brands, products, and mappings for a run."""
    run = _run_or_404(db, run_id)
    vertical = _vertical_or_404(db, run.vertical_id)
    brand_counts = _brand_counts(db, run_id)
    product_counts = _product_counts(db, run_id)
    brands = _brands_for_counts(db, brand_counts)
    products = _products_for_counts(db, product_counts)
    mappings = _mappings_for_products(db, run.vertical_id, list(product_counts.keys()))
    return _run_entities_response(run, vertical, brands, products, mappings, brand_counts, product_counts)


def _run_entities_response(
    run: Run,
    vertical: Vertical,
    brands: list[Brand],
    products: list[Product],
    mappings: list[RunEntityMapping],
    brand_counts: dict[int, int],
    product_counts: dict[int, int],
) -> RunEntitiesResponse:
    return RunEntitiesResponse(
        run_id=run.id, vertical_id=vertical.id, vertical_name=vertical.name,
        provider=run.provider, model_name=run.model_name, status=run.status.value,
        run_time=run.run_time, completed_at=run.completed_at,
        brands=_brand_items(brands, brand_counts),
        products=_product_items(products, product_counts), mappings=mappings,
    )


def _run_or_404(db: Session, run_id: int) -> Run:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return run


def _vertical_or_404(db: Session, vertical_id: int) -> Vertical:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {vertical_id} not found")
    return vertical


def _brand_counts(db: Session, run_id: int) -> dict[int, int]:
    rows = (
        db.query(BrandMention.brand_id, func.count(BrandMention.id))
        .join(LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id, BrandMention.mentioned)
        .group_by(BrandMention.brand_id)
        .all()
    )
    return {brand_id: count for brand_id, count in rows}


def _product_counts(db: Session, run_id: int) -> dict[int, int]:
    rows = (
        db.query(ProductMention.product_id, func.count(ProductMention.id))
        .join(LLMAnswer, LLMAnswer.id == ProductMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id, ProductMention.mentioned)
        .group_by(ProductMention.product_id)
        .all()
    )
    return {product_id: count for product_id, count in rows}


def _brands_for_counts(db: Session, counts: dict[int, int]) -> list[Brand]:
    if not counts:
        return []
    return db.query(Brand).filter(Brand.id.in_(counts.keys())).all()


def _products_for_counts(db: Session, counts: dict[int, int]) -> list[Product]:
    if not counts:
        return []
    return db.query(Product).options(joinedload(Product.brand)).filter(
        Product.id.in_(counts.keys())
    ).all()


def _brand_items(brands: list[Brand], counts: dict[int, int]) -> list[RunEntityBrand]:
    return [_brand_item(brand, counts.get(brand.id, 0)) for brand in brands]


def _product_items(products: list[Product], counts: dict[int, int]) -> list[RunEntityProduct]:
    return [_product_item(product, counts.get(product.id, 0)) for product in products]


def _brand_item(brand: Brand, count: int) -> RunEntityBrand:
    return RunEntityBrand(
        brand_id=brand.id,
        brand_name=format_entity_label(brand.original_name, brand.translated_name),
        original_name=brand.original_name,
        translated_name=brand.translated_name,
        mention_count=count,
    )


def _product_item(product: Product, count: int) -> RunEntityProduct:
    brand_name = ""
    if product.brand:
        brand_name = format_entity_label(product.brand.original_name, product.brand.translated_name)
    return RunEntityProduct(
        product_id=product.id,
        product_name=format_entity_label(product.original_name, product.translated_name),
        original_name=product.original_name,
        translated_name=product.translated_name,
        brand_id=product.brand_id,
        brand_name=brand_name,
        mention_count=count,
    )


def _mappings_for_products(
    db: Session,
    vertical_id: int,
    product_ids: list[int],
) -> list[RunEntityMapping]:
    rows = _mapping_rows(db, vertical_id, product_ids)
    return [_mapping_item(mapping, product, brand) for mapping, product, brand in rows]


def _mapping_rows(
    db: Session,
    vertical_id: int,
    product_ids: list[int],
) -> list[tuple[ProductBrandMapping, Product, Brand | None]]:
    if not product_ids:
        return []
    return db.query(ProductBrandMapping, Product, Brand).join(
        Product, Product.id == ProductBrandMapping.product_id
    ).outerjoin(
        Brand, Brand.id == ProductBrandMapping.brand_id
    ).filter(
        ProductBrandMapping.vertical_id == vertical_id,
        ProductBrandMapping.product_id.in_(product_ids),
    ).all()


def _mapping_item(
    mapping: ProductBrandMapping,
    product: Product,
    brand: Brand | None,
) -> RunEntityMapping:
    brand_name = format_entity_label(brand.original_name, brand.translated_name) if brand else ""
    return RunEntityMapping(
        product_id=product.id,
        product_name=format_entity_label(product.original_name, product.translated_name),
        brand_id=mapping.brand_id, brand_name=brand_name,
        confidence=mapping.confidence, source=mapping.source,
        is_validated=mapping.is_validated,
    )


async def _process_run_inline(run_id: int, vertical_id: int, engine) -> None:
    await asyncio.sleep(1)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = session_factory()
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
        if run and vertical:
            _complete_run_inline(db, run, vertical)
    finally:
        db.close()


def _complete_run_inline(db: Session, run: Run, vertical: Vertical) -> None:
    prompt = db.query(Prompt).filter(Prompt.vertical_id == vertical.id).first()
    brand = db.query(Brand).filter(Brand.vertical_id == vertical.id).first()
    if not prompt or not brand:
        run.status = RunStatus.COMPLETED
        run.completed_at = datetime.utcnow()
        commit_with_retry(db)
        return

    answer = LLMAnswer(
        run_id=run.id,
        prompt_id=prompt.id,
        raw_answer_zh=prompt.text_zh or prompt.text_en or "",
        raw_answer_en=prompt.text_en,
        tokens_in=0,
        tokens_out=0,
        cost_estimate=0.0,
    )
    db.add(answer)
    flush_with_retry(db)

    mention = BrandMention(
        llm_answer_id=answer.id,
        brand_id=brand.id,
        mentioned=True,
        rank=1,
        sentiment=Sentiment.NEUTRAL,
        evidence_snippets={"zh": [brand.display_name], "en": []},
    )
    db.add(mention)

    run.status = RunStatus.COMPLETED
    run.completed_at = datetime.utcnow()
    commit_with_retry(db)

    calculate_and_save_metrics(db, run.id)
    _mark_comparison_skipped_inline(db, run.id)


def _mark_comparison_skipped_inline(db: Session, run_id: int) -> None:
    from models import ComparisonRunStatus, RunComparisonConfig

    config = db.query(RunComparisonConfig).filter(RunComparisonConfig.run_id == run_id).first()
    if not config or not config.enabled:
        return
    if config.status != ComparisonRunStatus.PENDING:
        return
    config.status = ComparisonRunStatus.SKIPPED
    config.completed_at = datetime.utcnow()
    config.error_message = "Comparison skipped in RUN_TASKS_INLINE mode"
    commit_with_retry(db)
