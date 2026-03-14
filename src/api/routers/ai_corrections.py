import os

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models import Run, RunStatus, Vertical, get_db
from models.knowledge_database import get_knowledge_db, get_knowledge_db_write
from models.knowledge_domain import (
    KnowledgeAIAuditReviewItem,
    KnowledgeAIAuditReviewStatus,
    KnowledgeVertical,
)
from models.schemas import (
    AICorrectionCreateRequest,
    AICorrectionReportResponse,
    AICorrectionRunResponse,
    FeedbackSubmitRequest,
    FeedbackSubmitResponse,
)
from services.ai_corrections.config import merge_min_levels, merge_thresholds
from services.ai_corrections.model_selection import resolve_audit_model
from services.ai_corrections.persistence import (
    audit_run_or_none,
    create_audit_run,
    latest_audit_run,
    mark_review_item_applied,
    review_item_or_none,
)
from services.feedback_service import submit_feedback
from services.knowledge_verticals import ensure_vertical_alias, get_or_create_vertical
from services.ai_corrections.execution import execute_ai_correction_async
from workers.tasks import run_ai_correction
from services.knowledge_verticals import resolve_knowledge_vertical_id

router = APIRouter()

RUN_TASKS_INLINE = os.getenv("RUN_TASKS_INLINE", "false").lower() == "true"


@router.post("/runs/{run_id}/ai-corrections", response_model=AICorrectionRunResponse)
async def start_ai_correction(
    run_id: int,
    payload: AICorrectionCreateRequest | None = None,
    db: Session = Depends(get_db),
    knowledge_db: Session = Depends(get_knowledge_db_write),
) -> AICorrectionRunResponse:
    """
    Start an AI correction run for a completed tracking run.
    """
    run = _completed_run(db, run_id)
    vertical = _vertical(db, run.vertical_id)
    resolved = resolve_audit_model(db, (payload.provider if payload else None), (payload.model_name if payload else None))
    thresholds = merge_thresholds((payload.thresholds.model_dump(by_alias=True) if payload and payload.thresholds else None))
    min_levels = merge_min_levels((payload.min_confidence_levels.model_dump(by_alias=True) if payload and payload.min_confidence_levels else None))
    dry_run = bool(payload.dry_run) if payload and payload.dry_run is not None else False
    knowledge_vertical = _canonical_vertical(knowledge_db, vertical.name)
    audit = create_audit_run(
        knowledge_db,
        run.id,
        run.vertical_id,
        knowledge_vertical.id,
        resolved.requested_provider,
        resolved.requested_model,
        resolved.resolved_provider,
        resolved.resolved_model,
        resolved.resolved_route,
        thresholds.__dict__,
        {k: v.value for k, v in min_levels.__dict__.items()},
        dry_run,
    )
    knowledge_db.commit()
    if RUN_TASKS_INLINE:
        try:
            await execute_ai_correction_async(db, knowledge_db, audit.id)
        finally:
            knowledge_db.commit()
    else:
        run_ai_correction.delay(audit.id)
    return _audit_response(audit)


@router.get("/runs/{run_id}/ai-corrections", response_model=AICorrectionRunResponse | None)
async def get_latest_ai_correction(
    run_id: int,
    knowledge_db: Session = Depends(get_knowledge_db),
) -> AICorrectionRunResponse | None:
    """
    Get the latest AI correction run for this tracking run.
    """
    audit = latest_audit_run(knowledge_db, run_id)
    return _audit_response(audit) if audit else None


@router.get("/runs/{run_id}/ai-corrections/{audit_id}/report", response_model=AICorrectionReportResponse)
async def get_ai_correction_report(
    run_id: int,
    audit_id: int,
    knowledge_db: Session = Depends(get_knowledge_db),
) -> AICorrectionReportResponse:
    """
    Get metrics, clusters, and pending review items for an AI correction run.
    """
    audit = audit_run_or_none(knowledge_db, audit_id)
    if not audit or audit.run_id != run_id:
        raise HTTPException(status_code=404, detail="AI correction not found")
    items = knowledge_db.query(KnowledgeAIAuditReviewItem).filter(
        KnowledgeAIAuditReviewItem.audit_run_id == audit_id,
        KnowledgeAIAuditReviewItem.status == KnowledgeAIAuditReviewStatus.PENDING,
    ).order_by(KnowledgeAIAuditReviewItem.id.asc()).all()
    pending = [_review_item_response(i) for i in items]
    return AICorrectionReportResponse(
        audit_id=audit.id,
        run_id=audit.run_id,
        resolved_provider=audit.resolved_provider,
        resolved_model=audit.resolved_model,
        resolved_route=audit.resolved_route,
        brands=_metrics(audit.metrics.get("brands") or {}),
        products=_metrics(audit.metrics.get("products") or {}),
        mappings=_metrics(audit.metrics.get("mappings") or {}),
        clusters=[_cluster(c) for c in (audit.clusters.get("clusters") or [])],
        pending_review_items=pending,
    )


@router.post(
    "/runs/{run_id}/ai-corrections/{audit_id}/review-items/{item_id}/apply",
    response_model=FeedbackSubmitResponse,
)
async def apply_ai_review_item(
    run_id: int,
    audit_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    knowledge_db: Session = Depends(get_knowledge_db_write),
) -> FeedbackSubmitResponse:
    """
    Apply a low-confidence AI suggestion as user feedback.
    """
    audit = audit_run_or_none(knowledge_db, audit_id)
    if not audit or audit.run_id != run_id:
        raise HTTPException(status_code=404, detail="AI correction not found")
    item = review_item_or_none(knowledge_db, item_id)
    if not item or item.audit_run_id != audit_id:
        raise HTTPException(status_code=404, detail="Review item not found")
    if item.status != KnowledgeAIAuditReviewStatus.PENDING:
        raise HTTPException(status_code=409, detail="Review item already processed")
    request = FeedbackSubmitRequest(**(item.feedback_payload or {}))
    result = submit_feedback(db, knowledge_db, request, reviewer="user", reviewer_model=None)
    mark_review_item_applied(knowledge_db, item)
    knowledge_db.commit()
    return result


def _completed_run(db: Session, run_id: int) -> Run:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != RunStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Run is not completed")
    return run


def _vertical(db: Session, vertical_id: int) -> Vertical:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail="Vertical not found")
    return vertical


def _audit_response(audit) -> AICorrectionRunResponse:
    return AICorrectionRunResponse(
        audit_id=audit.id,
        run_id=audit.run_id,
        status=audit.status.value,
        requested_provider=audit.requested_provider,
        requested_model=audit.requested_model,
        resolved_provider=audit.resolved_provider,
        resolved_model=audit.resolved_model,
        resolved_route=audit.resolved_route,
        dry_run=bool(audit.dry_run),
    )


def _metrics(data: dict) -> dict:
    return {
        "precision": float(data.get("precision") or 0.0),
        "recall": float(data.get("recall") or 0.0),
        "true_positives": int(data.get("true_positives") or 0),
        "false_positives": int(data.get("false_positives") or 0),
        "false_negatives": int(data.get("false_negatives") or 0),
    }


def _cluster(item: dict) -> dict:
    return {
        "category": str(item.get("category") or ""),
        "count": int(item.get("count") or 0),
        "examples": [str(e) for e in (item.get("examples") or [])],
    }


def _review_item_response(item) -> dict:
    return {
        "id": int(item.id),
        "run_id": int(item.run_id),
        "llm_answer_id": int(item.llm_answer_id),
        "category": item.category,
        "action": item.action,
        "confidence_level": item.confidence_level,
        "confidence_score": float(item.confidence_score),
        "reason": item.reason,
        "evidence_quote_zh": item.evidence_quote_zh,
        "feedback_payload": item.feedback_payload or {},
    }


def _canonical_vertical(knowledge_db: Session, vertical_name: str) -> KnowledgeVertical:
    resolved_id = resolve_knowledge_vertical_id(knowledge_db, vertical_name)
    if resolved_id:
        row = knowledge_db.query(KnowledgeVertical).filter(KnowledgeVertical.id == int(resolved_id)).first()
        if row:
            return row
    row = get_or_create_vertical(knowledge_db, vertical_name)
    ensure_vertical_alias(knowledge_db, row.id, vertical_name)
    return row
