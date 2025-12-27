"""Service for finding and reusing LLM answers from previous runs."""

from typing import Optional

from sqlalchemy.orm import Session

from models import LLMAnswer, Prompt, Run
from models.domain import RunStatus


def find_reusable_answer(
    db: Session,
    run: Run,
    prompt_text_zh: str,
) -> Optional[LLMAnswer]:
    if not run.reuse_answers:
        return None

    completed_runs = (
        db.query(Run)
        .filter(
            Run.vertical_id == run.vertical_id,
            Run.id != run.id,
            Run.status == RunStatus.COMPLETED,
            Run.provider == run.provider,
            Run.model_name == run.model_name,
            Run.web_search_enabled == run.web_search_enabled,
        )
        .all()
    )

    if not completed_runs:
        return None

    completed_run_ids = [r.id for r in completed_runs]

    matching_prompt = (
        db.query(Prompt)
        .filter(
            Prompt.run_id.in_(completed_run_ids),
            Prompt.text_zh == prompt_text_zh,
        )
        .first()
    )

    if not matching_prompt:
        return None

    answer = (
        db.query(LLMAnswer)
        .filter(
            LLMAnswer.prompt_id == matching_prompt.id,
            LLMAnswer.run_id.in_(completed_run_ids),
        )
        .first()
    )

    return answer
