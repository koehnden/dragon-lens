from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models import get_db
from models.admin_schemas import (
    DemoPublishRequest,
    DemoPublishResponse,
    KnowledgeSyncRequest,
    KnowledgeSyncResponse,
)
from models.knowledge_database import get_knowledge_db_write
from services.admin_auth import (
    require_demo_publish_token,
    require_knowledge_sync_token,
)
from services.demo_publish import apply_demo_publish_request
from services.knowledge_sync import ingest_knowledge_sync_submission

router = APIRouter()


@router.post("/knowledge-sync", response_model=KnowledgeSyncResponse)
async def sync_knowledge_submission(
    payload: KnowledgeSyncRequest,
    _: None = Depends(require_knowledge_sync_token),
    knowledge_db: Session = Depends(get_knowledge_db_write),
) -> KnowledgeSyncResponse:
    try:
        vertical_id, created_counts, updated_counts = ingest_knowledge_sync_submission(
            knowledge_db,
            payload,
        )
        knowledge_db.commit()
    except ValueError as exc:
        knowledge_db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        knowledge_db.rollback()
        raise
    return KnowledgeSyncResponse(
        status="ok",
        canonical_vertical_id=vertical_id,
        created_counts=created_counts,
        updated_counts=updated_counts,
    )


@router.post("/demo-publish", response_model=DemoPublishResponse)
async def publish_demo_snapshot(
    payload: DemoPublishRequest,
    _: None = Depends(require_demo_publish_token),
    db: Session = Depends(get_db),
) -> DemoPublishResponse:
    try:
        vertical_id, run_count, brand_count, product_count = apply_demo_publish_request(
            db,
            payload,
        )
        db.commit()
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return DemoPublishResponse(
        status="ok",
        vertical_id=vertical_id,
        run_count=run_count,
        brand_count=brand_count,
        product_count=product_count,
    )
