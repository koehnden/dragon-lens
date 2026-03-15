import logging
from datetime import datetime

from sqlalchemy.orm import Session

from models import Brand, Prompt, Run, Vertical
from models.db_retry import commit_with_retry
from models.domain import RunStatus
from services.remote_llms import LLMRouter
from services.run_answer_service import fetch_answers_for_run
from services.run_extraction_service import extract_mentions_for_answer
from services.run_finalization_service import finalize_run_processing

logger = logging.getLogger(__name__)


def run_vertical_analysis_sync(
    db: Session, vertical_id: int, provider: str, model_name: str, run_id: int
) -> None:
    logger.info(
        "Starting vertical analysis: vertical=%s, provider=%s, model=%s, run=%s",
        vertical_id,
        provider,
        model_name,
        run_id,
    )

    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        if not run:
            raise ValueError(f"Run {run_id} not found")

        run.status = RunStatus.IN_PROGRESS

        vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
        if not vertical:
            raise ValueError(f"Vertical {vertical_id} not found")

        prompts = db.query(Prompt).filter(Prompt.run_id == run_id).all()
        if not prompts:
            raise ValueError(f"No prompts found for run {run_id}")

        brands = db.query(Brand).filter(Brand.vertical_id == vertical_id).all()
        if not brands:
            raise ValueError(f"No brands found for vertical {vertical_id}")

        llm_router = LLMRouter(db)
        resolution = llm_router.resolve(provider, model_name)
        run.route = resolution.route
        commit_with_retry(db)

        prepared_answers = fetch_answers_for_run(db, run, prompts, provider, model_name)

        results: list[dict] = []
        for prepared in prepared_answers:
            extraction_result = extract_mentions_for_answer(
                db,
                run_id,
                prepared.llm_answer.id,
                force_reextract=True,
            )
            if not extraction_result.ok:
                raise RuntimeError(
                    f"Extraction failed for prompt {prepared.item.prompt.id}: {extraction_result.error}"
                )
            results.append(
                {
                    "run_id": run_id,
                    "prompt_id": prepared.item.prompt.id,
                    "llm_answer_id": prepared.llm_answer.id,
                    "ok": True,
                    "reused": prepared.item.existing_answer is not None
                    or prepared.item.reusable_answer is not None,
                    "stage": extraction_result.stage,
                    "error": None,
                }
            )

        logger.info("Consolidating entities for run %s...", run_id)
        finalize_run_processing(db, run_id, results)
        logger.info("Completed vertical analysis: run=%s", run_id)
    except Exception as exc:
        logger.error("Error in vertical analysis: %s", exc, exc_info=True)
        run = db.query(Run).filter(Run.id == run_id).first()
        if run:
            run.status = RunStatus.FAILED
            run.error_message = str(exc)
            run.completed_at = datetime.utcnow()
            commit_with_retry(db)
        raise
