from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models import get_db
from models.knowledge_database import get_knowledge_db
from models.schemas import FeedbackSubmitRequest, FeedbackSubmitResponse
from services.feedback_service import submit_feedback

router = APIRouter()


@router.post("/feedback/submit", response_model=FeedbackSubmitResponse)
async def submit_feedback_endpoint(
    payload: FeedbackSubmitRequest,
    db: Session = Depends(get_db),
    knowledge_db: Session = Depends(get_knowledge_db),
) -> FeedbackSubmitResponse:
    """Submit user feedback to the knowledge database."""
    return submit_feedback(db, knowledge_db, payload)
