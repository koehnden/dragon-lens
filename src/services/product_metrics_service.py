from __future__ import annotations

from sqlalchemy.orm import Session

from metrics.metrics import AnswerMetrics, visibility_metrics
from models import LLMAnswer, ProductMention, Prompt, Run, RunProductMetrics


def calculate_and_save_run_product_metrics(db: Session, run_id: int) -> None:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")
    prompt_ids = _prompt_ids(db, run_id)
    mentions = _product_mentions(db, run_id)
    if not prompt_ids or not mentions:
        return
    db.query(RunProductMetrics).filter(RunProductMetrics.run_id == run_id).delete()
    _insert_product_metrics(db, run_id, prompt_ids, _to_answer_metrics(mentions))
    db.commit()


def _prompt_ids(db: Session, run_id: int) -> list[int]:
    return [int(pid) for (pid,) in db.query(Prompt.id).filter(Prompt.run_id == run_id).all()]


def _product_mentions(db: Session, run_id: int) -> list[ProductMention]:
    return (
        db.query(ProductMention)
        .join(LLMAnswer, LLMAnswer.id == ProductMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id, ProductMention.mentioned)
        .all()
    )


def _to_answer_metrics(mentions: list[ProductMention]) -> list[AnswerMetrics]:
    return [
        AnswerMetrics(
            prompt_id=m.llm_answer.prompt_id,
            brand=str(m.product_id),
            rank=m.rank,
            sentiment=m.sentiment.value,
        )
        for m in mentions
        if m.mentioned
    ]


def _insert_product_metrics(db: Session, run_id: int, prompt_ids: list[int], metrics_list: list[AnswerMetrics]) -> None:
    keys = sorted({m.brand for m in metrics_list if m.brand})
    for key in keys:
        competitors = [k for k in keys if k != key]
        metrics = visibility_metrics(prompt_ids=prompt_ids, mentions=metrics_list, brand=key, competitor_brands=competitors)
        db.add(RunProductMetrics(
            run_id=run_id,
            product_id=int(key),
            mention_rate=metrics["mention_rate"],
            share_of_voice=metrics["share_of_voice"],
            top_spot_share=metrics["top_spot_share"],
            sentiment_index=metrics["sentiment_index"],
            dragon_lens_visibility=metrics["dragon_lens_visibility"],
        ))
