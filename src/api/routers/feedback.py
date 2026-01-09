import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from config import settings
from models import Vertical, get_db
from models.knowledge_database import get_knowledge_db_write
from models.schemas import FeedbackSubmitRequest, FeedbackSubmitResponse
from services.feedback_service import submit_feedback
from services.feedback_sanity import (
    check_brand_feedback,
    check_product_feedback,
    check_translation_feedback,
)
from services.knowledge_size import knowledge_db_size_bytes

router = APIRouter()


@router.post("/feedback/submit", response_model=FeedbackSubmitResponse)
async def submit_feedback_endpoint(
    payload: FeedbackSubmitRequest,
    db: Session = Depends(get_db),
    knowledge_db: Session = Depends(get_knowledge_db_write),
) -> FeedbackSubmitResponse:
    """Submit user feedback to the knowledge database."""
    size = knowledge_db_size_bytes(knowledge_db)
    if size is not None and size >= settings.knowledge_db_max_bytes:
        raise HTTPException(status_code=507, detail="Knowledge database size limit exceeded")
    vertical = db.query(Vertical).filter(Vertical.id == payload.vertical_id).first()
    vertical_name = vertical.name if vertical else ""
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
            raise HTTPException(status_code=400, detail={"error": "feedback_rejected", "reasons": reasons})
    result = submit_feedback(db, knowledge_db, payload)
    if settings.feedback_trigger_rerun_enabled:
        try:
            from workers.tasks import start_run

            start_run.delay(payload.run_id, True, True)
        except Exception:
            pass
    return result
