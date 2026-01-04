from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from models import EntityType, Run, Vertical, get_db
from models.schemas import (
    CanonicalBrandResponse,
    CanonicalProductResponse,
    ConsolidationResultResponse,
    ValidateCandidateRequest,
    ValidationCandidateResponse,
)
from services.entity_consolidation import (
    consolidate_run,
    get_canonical_brands,
    get_canonical_products,
    get_pending_candidates,
    validate_candidate,
)

router = APIRouter()


@router.post("/runs/{run_id}/consolidate", response_model=ConsolidationResultResponse)
async def consolidate_entities(
    run_id: int,
    db: Session = Depends(get_db),
) -> ConsolidationResultResponse:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    result = consolidate_run(db, run_id)

    return ConsolidationResultResponse(
        brands_merged=result.brands_merged,
        products_merged=result.products_merged,
        brands_flagged=result.brands_flagged,
        products_flagged=result.products_flagged,
        canonical_brands_created=result.canonical_brands_created,
        canonical_products_created=result.canonical_products_created,
    )


@router.get(
    "/verticals/{vertical_id}/canonical-brands",
    response_model=List[CanonicalBrandResponse],
)
async def list_canonical_brands(
    vertical_id: int,
    db: Session = Depends(get_db),
) -> List[CanonicalBrandResponse]:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {vertical_id} not found")

    brands = get_canonical_brands(db, vertical_id)

    return [
        CanonicalBrandResponse(
            id=b.id,
            vertical_id=b.vertical_id,
            canonical_name=b.canonical_name,
            display_name=b.display_name,
            is_validated=b.is_validated,
            validation_source=b.validation_source,
            mention_count=b.mention_count,
            aliases=[a.alias for a in b.aliases],
            created_at=b.created_at,
        )
        for b in brands
    ]


@router.get(
    "/verticals/{vertical_id}/canonical-products",
    response_model=List[CanonicalProductResponse],
)
async def list_canonical_products(
    vertical_id: int,
    db: Session = Depends(get_db),
) -> List[CanonicalProductResponse]:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {vertical_id} not found")

    products = get_canonical_products(db, vertical_id)

    return [
        CanonicalProductResponse(
            id=p.id,
            vertical_id=p.vertical_id,
            canonical_brand_id=getattr(p, "canonical_brand_id", None) or getattr(p, "brand_id", None),
            canonical_name=p.canonical_name,
            display_name=p.display_name,
            is_validated=p.is_validated,
            validation_source=p.validation_source,
            mention_count=p.mention_count,
            aliases=[a.alias for a in p.aliases],
            created_at=p.created_at,
        )
        for p in products
    ]


@router.get(
    "/verticals/{vertical_id}/validation-candidates",
    response_model=List[ValidationCandidateResponse],
)
async def list_validation_candidates(
    vertical_id: int,
    entity_type: Optional[str] = Query(None, description="Filter by entity type: brand or product"),
    db: Session = Depends(get_db),
) -> List[ValidationCandidateResponse]:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {vertical_id} not found")

    type_filter = None
    if entity_type:
        if entity_type.lower() == "brand":
            type_filter = EntityType.BRAND
        elif entity_type.lower() == "product":
            type_filter = EntityType.PRODUCT
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid entity_type: {entity_type}. Must be 'brand' or 'product'",
            )

    candidates = get_pending_candidates(db, vertical_id, type_filter)

    return [
        ValidationCandidateResponse(
            id=c.id,
            vertical_id=c.vertical_id,
            entity_type=c.entity_type.value,
            name=c.name,
            canonical_id=c.canonical_id,
            mention_count=c.mention_count,
            status=c.status.value,
            reviewed_at=c.reviewed_at,
            reviewed_by=c.reviewed_by,
            rejection_reason=c.rejection_reason,
            created_at=c.created_at,
        )
        for c in candidates
    ]


@router.post(
    "/validation-candidates/{candidate_id}/validate",
    response_model=ValidationCandidateResponse,
)
async def validate_entity_candidate(
    candidate_id: int,
    request: ValidateCandidateRequest,
    db: Session = Depends(get_db),
) -> ValidationCandidateResponse:
    try:
        candidate = validate_candidate(
            db,
            candidate_id,
            request.approved,
            request.rejection_reason,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return ValidationCandidateResponse(
        id=candidate.id,
        vertical_id=candidate.vertical_id,
        entity_type=candidate.entity_type.value,
        name=candidate.name,
        canonical_id=candidate.canonical_id,
        mention_count=candidate.mention_count,
        status=candidate.status.value,
        reviewed_at=candidate.reviewed_at,
        reviewed_by=candidate.reviewed_by,
        rejection_reason=candidate.rejection_reason,
        created_at=candidate.created_at,
    )
