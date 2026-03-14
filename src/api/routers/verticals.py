"""API router for vertical management."""

import os
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from models import Brand, DailyMetrics, Run, RunMetrics, RunStatus, Vertical, get_db
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
    BrandResponse,
    DeleteVerticalResponse,
    FeedbackSubmitRequest,
    FeedbackSubmitResponse,
    RunInspectorPromptExport,
    VerticalCreate,
    VerticalResponse,
)
from services.ai_corrections.config import merge_min_levels, merge_thresholds
from services.ai_corrections.execution import execute_ai_correction_async
from services.ai_corrections.model_selection import resolve_audit_model
from services.ai_corrections.persistence import (
    audit_run_or_none,
    create_audit_run,
    latest_vertical_audit_run,
    mark_review_item_applied,
    review_item_or_none,
)
from services.feedback_service import submit_feedback
from services.knowledge_verticals import ensure_vertical_alias, get_or_create_vertical, resolve_knowledge_vertical_id
from services.run_inspector_export import build_vertical_inspector_export
from workers.tasks import run_ai_correction

router = APIRouter()

RUN_TASKS_INLINE = os.getenv("RUN_TASKS_INLINE", "false").lower() == "true"


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


@router.get("/{vertical_id}/models", response_model=List[str])
async def get_vertical_models(
    vertical_id: int,
    db: Session = Depends(get_db),
) -> List[str]:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {vertical_id} not found")

    models = (
        db.query(Run.model_name)
        .filter(Run.vertical_id == vertical_id, Run.status == RunStatus.COMPLETED)
        .distinct()
        .all()
    )

    return sorted([m[0] for m in models])


@router.get("/{vertical_id}/inspector-export", response_model=List[RunInspectorPromptExport])
async def export_vertical_inspector_data(
    vertical_id: int,
    db: Session = Depends(get_db),
) -> list[dict]:
    """
    Export run inspector prompt/answer data for all completed runs in this vertical.
    """
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {vertical_id} not found")
    return build_vertical_inspector_export(db, vertical_id)


@router.post("/{vertical_id}/ai-corrections", response_model=AICorrectionRunResponse)
async def start_vertical_ai_correction(
    vertical_id: int,
    payload: AICorrectionCreateRequest | None = None,
    db: Session = Depends(get_db),
    knowledge_db: Session = Depends(get_knowledge_db_write),
) -> AICorrectionRunResponse:
    """
    Start an AI correction run for all completed runs in this vertical (dry-run only).
    """
    vertical = _vertical_or_404(db, vertical_id)
    _require_completed_runs(db, vertical_id)
    resolved = resolve_audit_model(db, (payload.provider if payload else None), (payload.model_name if payload else None))
    thresholds = merge_thresholds((payload.thresholds.model_dump(by_alias=True) if payload and payload.thresholds else None))
    min_levels = merge_min_levels((payload.min_confidence_levels.model_dump(by_alias=True) if payload and payload.min_confidence_levels else None))
    knowledge_vertical = _canonical_vertical(knowledge_db, vertical.name)
    audit = create_audit_run(
        knowledge_db,
        0,
        vertical_id,
        knowledge_vertical.id,
        resolved.requested_provider,
        resolved.requested_model,
        resolved.resolved_provider,
        resolved.resolved_model,
        resolved.resolved_route,
        thresholds.__dict__,
        {k: v.value for k, v in min_levels.__dict__.items()},
        True,
        scope="vertical",
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


@router.get("/{vertical_id}/ai-corrections", response_model=AICorrectionRunResponse | None)
async def get_latest_vertical_ai_correction(
    vertical_id: int,
    knowledge_db: Session = Depends(get_knowledge_db),
) -> AICorrectionRunResponse | None:
    """
    Get the latest AI correction run for this vertical.
    """
    audit = latest_vertical_audit_run(knowledge_db, vertical_id)
    return _audit_response(audit) if audit else None


@router.get("/{vertical_id}/ai-corrections/{audit_id}/report", response_model=AICorrectionReportResponse)
async def get_vertical_ai_correction_report(
    vertical_id: int,
    audit_id: int,
    knowledge_db: Session = Depends(get_knowledge_db),
) -> AICorrectionReportResponse:
    """
    Get metrics, clusters, and pending review items for a vertical AI correction run.
    """
    audit = audit_run_or_none(knowledge_db, audit_id)
    if not audit or audit.scope != "vertical" or audit.tracking_vertical_id != vertical_id:
        raise HTTPException(status_code=404, detail="AI correction not found")
    items = knowledge_db.query(KnowledgeAIAuditReviewItem).filter(
        KnowledgeAIAuditReviewItem.audit_run_id == audit_id,
        KnowledgeAIAuditReviewItem.status == KnowledgeAIAuditReviewStatus.PENDING,
    ).order_by(KnowledgeAIAuditReviewItem.id.asc()).all()
    pending = [_review_item_response(i) for i in items]
    return AICorrectionReportResponse(
        audit_id=audit.id,
        run_id=0,
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
    "/{vertical_id}/ai-corrections/{audit_id}/review-items/{item_id}/apply",
    response_model=FeedbackSubmitResponse,
)
async def apply_vertical_ai_review_item(
    vertical_id: int,
    audit_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    knowledge_db: Session = Depends(get_knowledge_db_write),
) -> FeedbackSubmitResponse:
    """
    Apply a low-confidence AI suggestion as user feedback.
    """
    audit = audit_run_or_none(knowledge_db, audit_id)
    if not audit or audit.scope != "vertical" or audit.tracking_vertical_id != vertical_id:
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


@router.get("/{vertical_id}/brands", response_model=List[BrandResponse])
async def list_vertical_brands(
    vertical_id: int,
    user_input_only: bool = False,
    db: Session = Depends(get_db),
) -> List[Brand]:
    """
    List brands for a specific vertical.

    Args:
        vertical_id: Vertical ID
        user_input_only: Whether to return only user-input brands
        db: Database session

    Returns:
        List of brands

    Raises:
        HTTPException: If vertical not found
    """
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {vertical_id} not found")

    query = db.query(Brand).filter(Brand.vertical_id == vertical_id)
    if user_input_only:
        query = query.filter(Brand.is_user_input.is_(True))
    return query.order_by(Brand.id.asc()).all()


def _vertical_or_404(db: Session, vertical_id: int) -> Vertical:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {vertical_id} not found")
    return vertical


def _require_completed_runs(db: Session, vertical_id: int) -> None:
    exists = db.query(Run.id).filter(Run.vertical_id == vertical_id, Run.status == RunStatus.COMPLETED).first()
    if not exists:
        raise HTTPException(status_code=400, detail="No completed runs found for this vertical")


def _audit_response(audit) -> AICorrectionRunResponse:
    return AICorrectionRunResponse(
        audit_id=audit.id,
        run_id=int(audit.run_id),
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
