from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from models.knowledge_domain import (
    KnowledgeAIAuditReviewItem,
    KnowledgeAIAuditReviewStatus,
    KnowledgeAIAuditRun,
    KnowledgeAIAuditStatus,
)


def create_audit_run(
    knowledge_db: Session,
    run_id: int,
    vertical_id: int,
    requested_provider: str,
    requested_model: str,
    resolved_provider: str,
    resolved_model: str,
    resolved_route: str,
    thresholds: dict[str, Any],
    min_confidence_levels: dict[str, Any],
    dry_run: bool,
) -> KnowledgeAIAuditRun:
    row = KnowledgeAIAuditRun(
        run_id=run_id,
        vertical_id=vertical_id,
        requested_provider=requested_provider,
        requested_model=requested_model,
        resolved_provider=resolved_provider,
        resolved_model=resolved_model,
        resolved_route=resolved_route,
        thresholds=thresholds,
        min_confidence_levels=min_confidence_levels,
        dry_run=dry_run,
        status=KnowledgeAIAuditStatus.PENDING,
        metrics={},
        clusters={},
        auto_applied={},
    )
    knowledge_db.add(row)
    knowledge_db.flush()
    return row


def latest_audit_run(knowledge_db: Session, run_id: int) -> KnowledgeAIAuditRun | None:
    return (
        knowledge_db.query(KnowledgeAIAuditRun)
        .filter(KnowledgeAIAuditRun.run_id == run_id)
        .order_by(KnowledgeAIAuditRun.id.desc())
        .first()
    )


def audit_run_or_none(knowledge_db: Session, audit_id: int) -> KnowledgeAIAuditRun | None:
    return knowledge_db.query(KnowledgeAIAuditRun).filter(KnowledgeAIAuditRun.id == audit_id).first()


def set_audit_in_progress(knowledge_db: Session, audit: KnowledgeAIAuditRun) -> None:
    audit.status = KnowledgeAIAuditStatus.IN_PROGRESS


def set_audit_completed(knowledge_db: Session, audit: KnowledgeAIAuditRun) -> None:
    audit.status = KnowledgeAIAuditStatus.COMPLETED
    audit.completed_at = datetime.utcnow()


def set_audit_failed(knowledge_db: Session, audit: KnowledgeAIAuditRun, message: str) -> None:
    audit.status = KnowledgeAIAuditStatus.FAILED
    audit.error_message = message
    audit.completed_at = datetime.utcnow()


def save_audit_results(
    knowledge_db: Session,
    audit: KnowledgeAIAuditRun,
    metrics: dict,
    clusters: list[dict],
    auto_applied: dict,
    tokens_in: int,
    tokens_out: int,
    cost_estimate: float | None,
) -> None:
    audit.metrics = metrics
    audit.clusters = {"clusters": clusters}
    audit.auto_applied = auto_applied
    audit.tokens_in = tokens_in
    audit.tokens_out = tokens_out
    audit.cost_estimate = cost_estimate


def add_review_items(
    knowledge_db: Session,
    audit_id: int,
    run_id: int,
    review_items: list[dict[str, Any]],
) -> list[KnowledgeAIAuditReviewItem]:
    rows = [_review_row(audit_id, run_id, item) for item in review_items]
    knowledge_db.add_all(rows)
    knowledge_db.flush()
    return rows


def _review_row(audit_id: int, run_id: int, item: dict[str, Any]) -> KnowledgeAIAuditReviewItem:
    return KnowledgeAIAuditReviewItem(
        audit_run_id=audit_id,
        run_id=run_id,
        llm_answer_id=int(item.get("llm_answer_id") or 0),
        category=str(item.get("category") or ""),
        action=str(item.get("action") or ""),
        confidence_level=str(item.get("confidence_level") or ""),
        confidence_score=float(item.get("confidence_score") or 0.0),
        reason=str(item.get("reason") or ""),
        evidence_quote_zh=item.get("evidence_quote_zh"),
        feedback_payload=item.get("feedback_payload") or {},
        status=KnowledgeAIAuditReviewStatus.PENDING,
    )


def review_item_or_none(knowledge_db: Session, item_id: int) -> KnowledgeAIAuditReviewItem | None:
    return knowledge_db.query(KnowledgeAIAuditReviewItem).filter(KnowledgeAIAuditReviewItem.id == item_id).first()


def mark_review_item_applied(knowledge_db: Session, item: KnowledgeAIAuditReviewItem) -> None:
    item.status = KnowledgeAIAuditReviewStatus.APPLIED
    item.applied_at = datetime.utcnow()
