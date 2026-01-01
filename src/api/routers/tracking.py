"""API router for tracking job management."""

import asyncio
import logging
import os
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker

from models import Brand, BrandMention, LLMAnswer, Prompt, Run, Vertical, get_db
from models.domain import PromptLanguage, RunStatus, Sentiment
from models.schemas import (
    BrandMentionResponse,
    DeleteJobsResponse,
    LLMAnswerResponse,
    RunDetailedResponse,
    RunResponse,
    TrackingJobCreate,
    TrackingJobResponse,
)
from services.translater import format_entity_label
from services.metrics_service import calculate_and_save_metrics

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
        db.flush()

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
    db.flush()

    for prompt_data in job.prompts:
        prompt = Prompt(
            vertical_id=vertical.id,
            run_id=run.id,
            text_en=prompt_data.text_en,
            text_zh=prompt_data.text_zh,
            language_original=PromptLanguage(prompt_data.language_original),
        )
        db.add(prompt)

    db.commit()
    db.refresh(run)

    if RUN_TASKS_INLINE:
        engine = db.get_bind()
        asyncio.create_task(_process_run_inline(run.id, vertical.id, engine))
        return TrackingJobResponse(
            run_id=run.id,
            vertical_id=vertical.id,
            provider=job.provider,
            model_name=job.model_name,
            status=run.status.value,
            message="Tracking job queued for inline processing."
        )

    from workers.tasks import run_vertical_analysis

    enqueue_message = "Tracking job created successfully. Processing will start shortly."
    try:
        run_vertical_analysis.delay(vertical.id, job.provider, job.model_name, run.id)
    except Exception as exc:  # pragma: no cover - defensive logging
        logger.warning(
            "Failed to enqueue vertical analysis for run %s: %s", run.id, exc
        )
        run.error_message = str(exc)
        db.commit()
        enqueue_message = (
            "Tracking job created, but background processing could not be enqueued. "
            "Please ensure the Celery worker and broker are available."
        )

    return TrackingJobResponse(
        run_id=run.id,
        vertical_id=vertical.id,
        provider=job.provider,
        model_name=job.model_name,
        status=run.status.value,
        message=enqueue_message,
    )


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

    db.commit()

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
    1. Verify the run exists and is in pending status
    2. Enqueue a Celery task to reprocess the run
    3. The task will reuse existing LLM answers and re-run extraction

    Args:
        run_id: Run ID to reprocess
        db: Database session

    Returns:
        Status message

    Raises:
        HTTPException: If run not found or not in pending status
    """
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    if run.status != RunStatus.PENDING:
        raise HTTPException(
            status_code=400,
            detail=f"Run {run_id} is not in pending status (current: {run.status.value})"
        )

    vertical = db.query(Vertical).filter(Vertical.id == run.vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {run.vertical_id} not found")

    if RUN_TASKS_INLINE:
        engine = db.get_bind()
        asyncio.create_task(_process_run_inline(run.id, vertical.id, engine))
        return {"message": f"Run {run_id} queued for inline reprocessing", "run_id": run_id}

    from workers.tasks import run_vertical_analysis

    try:
        run_vertical_analysis.delay(vertical.id, run.provider, run.model_name, run.id)
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
        status=run.status.value,
        run_time=run.run_time,
        completed_at=run.completed_at,
        error_message=run.error_message,
        answers=answers_data,
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
        db.commit()
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
    db.flush()

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
    db.commit()

    calculate_and_save_metrics(db, run.id)
