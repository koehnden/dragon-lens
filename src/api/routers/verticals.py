"""API router for vertical management."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from src.models import Vertical, get_db
from src.models.schemas import VerticalCreate, VerticalResponse

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
