"""API router for tracking job management."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models import Brand, Prompt, Run, Vertical, get_db
from models.domain import PromptLanguage, RunStatus
from models.schemas import RunResponse, TrackingJobCreate, TrackingJobResponse

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
