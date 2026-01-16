from __future__ import annotations

import asyncio

from sqlalchemy.orm import Session

from models import Run, Vertical
from services.ai_corrections.config import merge_min_levels, merge_thresholds
from services.ai_corrections.persistence import (
    add_review_items,
    add_applied_items,
    audit_run_or_none,
    save_audit_results,
    set_audit_completed,
    set_audit_failed,
    set_audit_in_progress,
)
from services.ai_corrections.runner import run_audit_batches
from services.ai_corrections.service import auto_feedback_payload, build_report, review_items_payloads
from services.feedback_service import submit_feedback
from services.remote_llms import LLMRouter
from services.run_inspector_export import build_run_inspector_export, build_vertical_inspector_export
from models.schemas import FeedbackSubmitRequest


def execute_ai_correction(db: Session, knowledge_db: Session, audit_id: int) -> dict:
    audit = audit_run_or_none(knowledge_db, audit_id)
    if not audit:
        raise ValueError(f"AI audit {audit_id} not found")
    set_audit_in_progress(knowledge_db, audit)
    try:
        return _run_sync(db, knowledge_db, audit)
    except Exception as exc:
        set_audit_failed(knowledge_db, audit, str(exc))
        raise


async def execute_ai_correction_async(db: Session, knowledge_db: Session, audit_id: int) -> dict:
    audit = audit_run_or_none(knowledge_db, audit_id)
    if not audit:
        raise ValueError(f"AI audit {audit_id} not found")
    set_audit_in_progress(knowledge_db, audit)
    try:
        return await _run_async(db, knowledge_db, audit)
    except Exception as exc:
        set_audit_failed(knowledge_db, audit, str(exc))
        raise


def _run_sync(db: Session, knowledge_db: Session, audit) -> dict:
    run, vertical, export, run_id, tracking_vertical_id = _audit_context(db, audit)
    thresholds = merge_thresholds(audit.thresholds)
    min_levels = merge_min_levels(audit.min_confidence_levels)
    items, tokens_in, tokens_out = _run_coroutine(_audit_items(db, audit, vertical.name, export))
    report = build_report(export, items, thresholds, min_levels, run_id, audit.vertical_id, tracking_vertical_id)
    applied = _apply_feedback(db, knowledge_db, run, audit, report) if run else {}
    save_audit_results(knowledge_db, audit, report["metrics"], report["clusters"], applied, tokens_in, tokens_out, None)
    add_review_items(knowledge_db, audit.id, report["review_suggestions"])
    set_audit_completed(knowledge_db, audit)
    return {"audit_id": audit.id, "status": audit.status.value}


async def _run_async(db: Session, knowledge_db: Session, audit) -> dict:
    run, vertical, export, run_id, tracking_vertical_id = _audit_context(db, audit)
    thresholds = merge_thresholds(audit.thresholds)
    min_levels = merge_min_levels(audit.min_confidence_levels)
    items, tokens_in, tokens_out = await _audit_items(db, audit, vertical.name, export)
    report = build_report(export, items, thresholds, min_levels, run_id, audit.vertical_id, tracking_vertical_id)
    applied = _apply_feedback(db, knowledge_db, run, audit, report) if run else {}
    save_audit_results(knowledge_db, audit, report["metrics"], report["clusters"], applied, tokens_in, tokens_out, None)
    add_review_items(knowledge_db, audit.id, report["review_suggestions"])
    set_audit_completed(knowledge_db, audit)
    return {"audit_id": audit.id, "status": audit.status.value}


async def _audit_items(db: Session, audit, vertical_name: str, export: list[dict]) -> tuple[list[dict], int, int]:
    llm_router = LLMRouter(db)
    return await run_audit_batches(llm_router, audit.resolved_provider, audit.resolved_model, vertical_name, export, batch_size=5)


def _apply_feedback(db: Session, knowledge_db: Session, run: Run, audit, report: dict) -> dict:
    suggestions = report.get("auto_suggestions") or []
    if audit.dry_run or not suggestions:
        return {}
    payload = auto_feedback_payload(run.id, run.vertical_id, audit.vertical_id, suggestions)
    request = FeedbackSubmitRequest(**payload)
    submit_feedback(db, knowledge_db, request, reviewer=audit.resolved_model, reviewer_model=f"{audit.resolved_provider}:{audit.resolved_model}")
    add_applied_items(
        knowledge_db,
        audit.id,
        review_items_payloads(suggestions, run.id, run.vertical_id, audit.vertical_id),
    )
    return _counts(suggestions)


def _counts(items: list[dict]) -> dict:
    counts: dict[str, int] = {}
    for item in items:
        key = str(item.get("action") or "")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _run_row(db: Session, run_id: int) -> Run:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")
    return run


def _vertical_row(db: Session, vertical_id: int) -> Vertical:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise ValueError(f"Vertical {vertical_id} not found")
    return vertical


def _audit_context(db: Session, audit) -> tuple[Run | None, Vertical, list[dict], int, int]:
    if str(getattr(audit, "scope", "run")) == "vertical":
        tracking_vertical_id = int(getattr(audit, "tracking_vertical_id", 0) or 0)
        vertical = _vertical_row(db, tracking_vertical_id)
        export = build_vertical_inspector_export(db, tracking_vertical_id)
        return None, vertical, export, 0, tracking_vertical_id
    run = _run_row(db, int(audit.run_id))
    vertical = _vertical_row(db, int(run.vertical_id))
    export = build_run_inspector_export(db, int(run.id))
    return run, vertical, export, int(run.id), int(run.vertical_id)


def _run_coroutine(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
