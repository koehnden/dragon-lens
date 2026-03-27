import logging
from datetime import datetime
from typing import List

from celery import Task, chord, group
from sqlalchemy.orm import Session

from models import Prompt, Run
from models.database import SessionLocal
from models.db_retry import commit_with_retry
from models.domain import LLMRoute, RunStatus
from services.brand_recognition import extract_entities
from services.entity_consolidation import consolidate_run
from services.remote_llms import LLMRouter
from services.run_analysis_service import run_vertical_analysis_sync
from services.run_answer_service import ensure_llm_answer_for_prompt
from services.run_extraction_service import (
    ExtractionTaskResult,
    collect_all_snippets as _collect_all_snippets,
    create_product_mentions as _create_product_mentions,
    extract_mentions_for_answer,
    get_translated_snippets as _get_translated_snippets,
)
from services.run_finalization_service import (
    finalize_run_processing,
    should_fail_run as _should_fail_run,
)
from workers.celery_app import celery_app

logger = logging.getLogger(__name__)

__all__ = [
    "DatabaseTask",
    "start_run",
    "ensure_llm_answer",
    "ensure_extraction",
    "finalize_run",
    "run_vertical_analysis",
    "translate_text",
    "extract_brand_mentions",
    "classify_sentiment",
    "consolidate_run",
    "_collect_all_snippets",
    "_get_translated_snippets",
    "_create_product_mentions",
    "_should_fail_run",
]


class DatabaseTask(Task):
    _db: Session | None = None

    @property
    def db(self) -> Session:
        if self._db is None:
            self._db = SessionLocal()
        return self._db

    def after_return(self, *args, **kwargs):
        if self._db is not None:
            self._db.close()
            self._db = None


def _prompt_id_list(db: Session, run_id: int) -> list[int]:
    return [
        prompt_id
        for (prompt_id,) in db.query(Prompt.id)
        .filter(Prompt.run_id == run_id)
        .order_by(Prompt.id)
        .all()
    ]


def _llm_queue(route: LLMRoute) -> str:
    return "local_llm" if route == LLMRoute.LOCAL else "remote_llm"


def _extraction_payload(payload: dict, result: ExtractionTaskResult) -> dict:
    return result.to_payload(payload)


@celery_app.task(base=DatabaseTask, bind=True)
def start_run(
    self: DatabaseTask,
    run_id: int,
    force_reextract: bool = False,
    skip_entity_consolidation: bool = False,
) -> dict:
    run = self.db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    llm_router = LLMRouter(self.db)
    resolution = llm_router.resolve(run.provider, run.model_name)
    run.route = resolution.route
    run.status = RunStatus.IN_PROGRESS
    run.error_message = None
    run.completed_at = None
    commit_with_retry(self.db)

    prompt_ids = _prompt_id_list(self.db, run_id)
    if not prompt_ids:
        run.status = RunStatus.FAILED
        run.error_message = f"No prompts found for run {run_id}"
        run.completed_at = datetime.utcnow()
        commit_with_retry(self.db)
        return {"run_id": run_id, "prompt_count": 0}

    header = []
    llm_queue = _llm_queue(resolution.route)
    for prompt_id in prompt_ids:
        header.append(
            ensure_llm_answer.s(run_id, prompt_id).set(queue=llm_queue)
            | ensure_extraction.s(run_id, force_reextract).set(queue="ollama_extract")
        )

    callback = finalize_run.s(run_id, force_reextract, skip_entity_consolidation).set(
        queue="default"
    )
    chord(group(header))(callback)
    return {"run_id": run_id, "prompt_count": len(prompt_ids)}


@celery_app.task(base=DatabaseTask, bind=True)
def ensure_llm_answer(self: DatabaseTask, run_id: int, prompt_id: int) -> dict:
    return ensure_llm_answer_for_prompt(self.db, run_id, prompt_id).to_payload()


@celery_app.task(base=DatabaseTask, bind=True)
def ensure_extraction(
    self: DatabaseTask, payload: dict, run_id: int, force_reextract: bool = False
) -> dict:
    if not payload.get("ok") or not payload.get("llm_answer_id"):
        return {**payload, "ok": False, "stage": "extraction_skipped", "error": payload.get("error")}

    result = extract_mentions_for_answer(
        self.db,
        run_id,
        int(payload["llm_answer_id"]),
        force_reextract=force_reextract,
    )
    return _extraction_payload(payload, result)


@celery_app.task(base=DatabaseTask, bind=True)
def finalize_run(
    self: DatabaseTask,
    results: list[dict],
    run_id: int,
    force_reextract: bool = False,
    skip_entity_consolidation: bool = False,
) -> dict:
    return finalize_run_processing(
        self.db,
        run_id,
        results,
        force_reextract=force_reextract,
        skip_entity_consolidation=skip_entity_consolidation,
    ).to_payload()


@celery_app.task(base=DatabaseTask, bind=True)
def run_vertical_analysis(
    self: DatabaseTask, vertical_id: int, provider: str, model_name: str, run_id: int
):
    return run_vertical_analysis_sync(
        self.db, vertical_id, provider, model_name, run_id
    )


@celery_app.task
def translate_text(text: str, source_lang: str, target_lang: str) -> str:
    logger.info("Translating from %s to %s", source_lang, target_lang)
    return f"[TODO: Translation of: {text}]"


@celery_app.task
def extract_brand_mentions(answer_text: str, brands: List[dict]) -> List[dict]:
    logger.info("Extracting brand mentions")
    if not brands:
        return []
    primary = brands[0]
    aliases = primary.get("aliases") or {"zh": [], "en": []}
    result = extract_entities(answer_text, primary.get("display_name", ""), aliases)
    return [
        {"canonical": name, "mentions": surfaces}
        for name, surfaces in result.brands.items()
    ]


@celery_app.task
def classify_sentiment(text: str) -> str:
    logger.info("Classifying sentiment")
    return "neutral"
