"""API router for vertical management."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models import DailyMetrics, Run, RunMetrics, RunStatus, Vertical, get_db
from models.schemas import DeleteVerticalResponse, VerticalCreate, VerticalResponse

router = APIRouter()


@router.post("", response_model=VerticalResponse, status_code=201)
async def create_vertical(
    vertical: VerticalCreate,
    db: Session = Depends(get_db),
) -> Vertical:
    """
    Create a new vertical.

    Args:
        vertical: Vertical data to create
        db: Database session

    Returns:
        Created vertical

    Raises:
        HTTPException: If vertical with same name already exists
    """
    existing = db.query(Vertical).filter(Vertical.name == vertical.name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Vertical '{vertical.name}' already exists")

    db_vertical = Vertical(
        name=vertical.name,
        description=vertical.description,
    )
    db.add(db_vertical)
    db.commit()
    db.refresh(db_vertical)

    return db_vertical


@router.get("", response_model=List[VerticalResponse])
async def list_verticals(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
) -> List[Vertical]:
    """
    List all verticals.

    Args:
        skip: Number of records to skip
        limit: Maximum number of records to return
        db: Database session

    Returns:
        List of verticals
    """
    verticals = db.query(Vertical).offset(skip).limit(limit).all()
    return verticals


@router.get("/{vertical_id}", response_model=VerticalResponse)
async def get_vertical(
    vertical_id: int,
    db: Session = Depends(get_db),
) -> Vertical:
    """
    Get a specific vertical by ID.

    Args:
        vertical_id: Vertical ID
        db: Database session

    Returns:
        Vertical data

    Raises:
        HTTPException: If vertical not found
    """
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {vertical_id} not found")

    return vertical


@router.delete("/{vertical_id}", response_model=DeleteVerticalResponse)
async def delete_vertical(
    vertical_id: int,
    db: Session = Depends(get_db),
) -> DeleteVerticalResponse:
    """
    Delete a vertical and all associated data.

    Args:
        vertical_id: Vertical ID
        db: Database session

    Returns:
        Deletion confirmation with count of deleted runs

    Raises:
        HTTPException: If vertical not found or has running jobs
    """
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(
            status_code=404,
            detail={
                "error": {
                    "code": "VERTICAL_NOT_FOUND",
                    "message": f"No vertical found with ID '{vertical_id}'",
                }
            },
        )

    active_runs = (
        db.query(Run)
        .filter(
            Run.vertical_id == vertical_id,
            Run.status.in_([RunStatus.PENDING, RunStatus.IN_PROGRESS]),
        )
        .all()
    )

    if active_runs:
        active_run_ids = [run.id for run in active_runs]
        raise HTTPException(
            status_code=409,
            detail={
                "error": {
                    "code": "DELETE_CONFLICT",
                    "message": f"Cannot delete vertical with {len(active_runs)} runs still in progress. Wait for completion or delete those runs first.",
                    "details": {"running_run_ids": active_run_ids},
                }
            },
        )

    total_runs = db.query(Run).filter(Run.vertical_id == vertical_id).count()
    vertical_name = vertical.name

    db.query(DailyMetrics).filter(DailyMetrics.vertical_id == vertical_id).delete()
    db.query(RunMetrics).filter(
        RunMetrics.run_id.in_(
            db.query(Run.id).filter(Run.vertical_id == vertical_id)
        )
    ).delete(synchronize_session=False)

    db.delete(vertical)
    db.commit()

    return DeleteVerticalResponse(
        vertical_id=vertical_id,
        deleted=True,
        deleted_runs_count=total_runs,
        message=f"Vertical '{vertical_name}' and {total_runs} associated runs have been deleted",
    )
