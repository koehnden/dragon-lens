from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from models.knowledge_database import get_knowledge_db
from models.knowledge_domain import KnowledgeVertical
from models.schemas import KnowledgeVerticalResponse

router = APIRouter()


@router.get("/knowledge/verticals", response_model=List[KnowledgeVerticalResponse])
async def list_knowledge_verticals(
    knowledge_db: Session = Depends(get_knowledge_db),
) -> List[KnowledgeVertical]:
    """List canonical verticals stored in the knowledge database."""
    return _knowledge_verticals(knowledge_db)


def _knowledge_verticals(knowledge_db: Session) -> List[KnowledgeVertical]:
    return knowledge_db.query(KnowledgeVertical).order_by(
        KnowledgeVertical.name.asc()
    ).all()
