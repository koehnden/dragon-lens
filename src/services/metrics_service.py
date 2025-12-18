import time
from functools import wraps
from typing import List

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from metrics.metrics import AnswerMetrics, visibility_metrics
from models import Brand, BrandMention, LLMAnswer, Prompt, Run, RunMetrics
from models.domain import EntityType


def retry_on_db_lock(max_retries: int = 5, base_delay: float = 0.1, max_delay: float = 2.0):
    """Decorator to retry database operations on SQLite lock errors."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except OperationalError as e:
                    last_exception = e
                    if "database is locked" in str(e).lower():
                        if attempt < max_retries - 1:
                            delay = min(base_delay * (2 ** attempt), max_delay)
                            print(f"Database locked, retrying metrics calculation in {delay:.2f}s (attempt {attempt + 1}/{max_retries})")
                            time.sleep(delay)
                            continue
                    # Re-raise if not a lock error or max retries reached
                    raise
            # This should not be reached, but just in case
            raise last_exception
        return wrapper
    return decorator


@retry_on_db_lock()
def calculate_and_save_metrics(db: Session, run_id: int) -> None:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    vertical_id = run.vertical_id

    brands = (
        db.query(Brand)
        .filter(Brand.vertical_id == vertical_id, Brand.entity_type == EntityType.BRAND)
        .all()
    )
    prompts = db.query(Prompt).filter(Prompt.vertical_id == vertical_id).all()

    if not brands or not prompts:
        return

    prompt_ids = [p.id for p in prompts]

    answers = db.query(LLMAnswer).filter(LLMAnswer.run_id == run_id).all()
    if not answers:
        return

    mentions = (
        db.query(BrandMention)
        .join(LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id)
        .all()
    )

    answer_metrics_list = _to_metrics(mentions)

    brand_names = [b.display_name for b in brands]

    for brand in brands:
        competitor_brands = [b for b in brand_names if b != brand.display_name]

        metrics = visibility_metrics(
            prompt_ids=prompt_ids,
            mentions=answer_metrics_list,
            brand=brand.display_name,
            competitor_brands=competitor_brands,
        )

        run_metrics = RunMetrics(
            run_id=run_id,
            brand_id=brand.id,
            mention_rate=metrics["mention_rate"],
            share_of_voice=metrics["share_of_voice"],
            top_spot_share=metrics["top_spot_share"],
            sentiment_index=metrics["sentiment_index"],
            dragon_lens_visibility=metrics["dragon_lens_visibility"],
        )
        db.add(run_metrics)

    db.commit()


def _to_metrics(mentions: List[BrandMention]) -> List[AnswerMetrics]:
    metrics_list = []
    for mention in mentions:
        if not mention.mentioned:
            continue
        prompt_id = mention.llm_answer.prompt_id
        brand_name = mention.brand.display_name
        metrics_list.append(
            AnswerMetrics(
                prompt_id=prompt_id,
                brand=brand_name,
                rank=mention.rank,
                sentiment=mention.sentiment.value,
            )
        )
    return metrics_list
