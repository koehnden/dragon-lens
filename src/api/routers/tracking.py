"""API router for tracking job management."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models import Brand, BrandMention, LLMAnswer, Prompt, Run, Vertical, get_db
from models.domain import PromptLanguage, RunStatus
from models.schemas import (
    BrandMentionResponse,
    LLMAnswerResponse,
    RunDetailedResponse,
    RunResponse,
    TrackingJobCreate,
    TrackingJobResponse,
)

router = APIRouter()


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
    vertical = db.query(Vertical).filter(Vertical.name == job.vertical_name).first()
    if not vertical:
        vertical = Vertical(
            name=job.vertical_name,
            description=job.vertical_description,
        )
        db.add(vertical)
        db.flush()

    for brand_data in job.brands:
        brand = Brand(
            vertical_id=vertical.id,
            display_name=brand_data.display_name,
            aliases=brand_data.aliases,
        )
        db.add(brand)

    for prompt_data in job.prompts:
        prompt = Prompt(
            vertical_id=vertical.id,
            text_en=prompt_data.text_en,
            text_zh=prompt_data.text_zh,
            language_original=PromptLanguage(prompt_data.language_original),
        )
        db.add(prompt)

    run = Run(
        vertical_id=vertical.id,
        model_name=job.model_name,
        status=RunStatus.PENDING,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    from workers.tasks import run_vertical_analysis
    run_vertical_analysis.delay(vertical.id, job.model_name, run.id)

    return TrackingJobResponse(
        run_id=run.id,
        vertical_id=vertical.id,
        model_name=job.model_name,
        status=run.status.value,
        message="Tracking job created successfully. Processing will start shortly.",
    )


@router.get("/runs", response_model=List[RunResponse])
async def list_runs(
    vertical_id: int | None = None,
    model_name: str | None = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[Run]:
    """
    List tracking runs with optional filters.

    Args:
        vertical_id: Filter by vertical ID
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
            mentions_data.append(
                BrandMentionResponse(
                    brand_id=mention.brand_id,
                    brand_name=brand.display_name if brand else "Unknown",
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
                raw_answer_zh=llm_answer.raw_answer_zh,
                raw_answer_en=llm_answer.raw_answer_en,
                mentions=mentions_data,
                created_at=llm_answer.created_at,
            )
        )

    return RunDetailedResponse(
        id=run.id,
        vertical_id=run.vertical_id,
        vertical_name=vertical.name if vertical else "Unknown",
        model_name=run.model_name,
        status=run.status.value,
        run_time=run.run_time,
        completed_at=run.completed_at,
        error_message=run.error_message,
        answers=answers_data,
    )
