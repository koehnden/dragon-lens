import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from models import get_db
from models.knowledge_database import get_knowledge_db, get_knowledge_db_write
from models.schemas import (
    FeedbackCandidatesResponse,
    FeedbackSubmitRequest,
    FeedbackSubmitResponse,
    FeedbackVerticalAliasRequest,
    FeedbackVerticalAliasResponse,
)
from services.feedback_candidates import feedback_candidates
from services.feedback_service import (
    save_vertical_alias,
    submit_feedback,
    validate_feedback_request,
)
from services.feedback_sanity import (
    check_brand_feedback,
    check_product_feedback,
    check_translation_feedback,
)
from services.knowledge_size import knowledge_db_size_bytes

router = APIRouter()


@router.get("/feedback/candidates", response_model=FeedbackCandidatesResponse)
async def list_feedback_candidates(
    vertical_id: int,
    db: Session = Depends(get_db),
    knowledge_db: Session = Depends(get_knowledge_db),
) -> FeedbackCandidatesResponse:
    """List unresolved feedback candidates for a vertical."""
    return feedback_candidates(db, knowledge_db, vertical_id)


@router.post("/feedback/vertical-alias", response_model=FeedbackVerticalAliasResponse)
async def save_feedback_vertical_alias(
    payload: FeedbackVerticalAliasRequest,
    db: Session = Depends(get_db),
    knowledge_db: Session = Depends(get_knowledge_db_write),
) -> FeedbackVerticalAliasResponse:
    """Map a local vertical name into a canonical knowledge vertical."""
    return save_vertical_alias(
        db, knowledge_db, payload.vertical_id, payload.canonical_vertical
    )


@router.post("/feedback/submit", response_model=FeedbackSubmitResponse)
async def submit_feedback_endpoint(
    payload: FeedbackSubmitRequest,
    db: Session = Depends(get_db),
    knowledge_db: Session = Depends(get_knowledge_db_write),
) -> FeedbackSubmitResponse:
    """Submit user feedback to the knowledge database."""
    vertical = validate_feedback_request(db, payload)
    vertical_name = vertical.name
    size = knowledge_db_size_bytes(knowledge_db)
    if size is not None and size >= settings.knowledge_db_max_bytes:
        raise HTTPException(
            status_code=507, detail="Knowledge database size limit exceeded"
        )
    if settings.feedback_sanity_checks_enabled:
        try:
            results = await asyncio.gather(
                check_brand_feedback(payload, vertical_name),
                check_product_feedback(payload, vertical_name),
                check_translation_feedback(payload, vertical_name),
            )
        except Exception:
            raise HTTPException(status_code=503, detail="Feedback checks unavailable")
        failures = [r for r in results if not r[0]]
        if failures:
            reasons = [reason for _, rs in failures for reason in rs]
            raise HTTPException(
                status_code=400,
                detail={"error": "feedback_rejected", "reasons": reasons},
            )
    result = submit_feedback(db, knowledge_db, payload)
    if settings.feedback_trigger_rerun_enabled:
        try:
            from workers.tasks import start_run

            start_run.delay(payload.run_id, True, True)
        except Exception:
            pass
    return result
