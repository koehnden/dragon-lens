from __future__ import annotations

from sqlalchemy.orm import Session

from metrics.metrics import dragon_lens_visibility_score
from models import (
    BrandMention,
    ComparisonSentimentObservation,
    EntityType,
    LLMAnswer,
    ProductMention,
    RunMetrics,
    RunProductMetrics,
    Sentiment,
)


def update_run_metrics_with_comparison_sentiment(db: Session, run_id: int) -> None:
    _update_brand_metrics(db, run_id)
    _update_product_metrics(db, run_id)
    db.commit()


def _update_brand_metrics(db: Session, run_id: int) -> None:
    main = _counts_from_brand_mentions(db, run_id)
    comp = _counts_from_comparison(db, run_id, EntityType.BRAND)
    for row in db.query(RunMetrics).filter(RunMetrics.run_id == run_id).all():
        pos, neu, neg = _merge_counts(main.get(row.brand_id), comp.get(row.brand_id))
        row.sentiment_index = _sentiment_index(pos, neu, neg)
        row.dragon_lens_visibility = dragon_lens_visibility_score(row.share_of_voice, row.top_spot_share, row.sentiment_index)


def _update_product_metrics(db: Session, run_id: int) -> None:
    main = _counts_from_product_mentions(db, run_id)
    comp = _counts_from_comparison(db, run_id, EntityType.PRODUCT)
    for row in db.query(RunProductMetrics).filter(RunProductMetrics.run_id == run_id).all():
        pos, neu, neg = _merge_counts(main.get(row.product_id), comp.get(row.product_id))
        row.sentiment_index = _sentiment_index(pos, neu, neg)
        row.dragon_lens_visibility = dragon_lens_visibility_score(row.share_of_voice, row.top_spot_share, row.sentiment_index)


def _counts_from_brand_mentions(db: Session, run_id: int) -> dict[int, tuple[int, int, int]]:
    mentions = (
        db.query(BrandMention.brand_id, BrandMention.sentiment)
        .join(LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id, BrandMention.mentioned)
        .all()
    )
    return _counts_by_id(mentions)


def _counts_from_product_mentions(db: Session, run_id: int) -> dict[int, tuple[int, int, int]]:
    mentions = (
        db.query(ProductMention.product_id, ProductMention.sentiment)
        .join(LLMAnswer, LLMAnswer.id == ProductMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id, ProductMention.mentioned)
        .all()
    )
    return _counts_by_id(mentions)


def _counts_from_comparison(db: Session, run_id: int, entity_type: EntityType) -> dict[int, tuple[int, int, int]]:
    rows = (
        db.query(ComparisonSentimentObservation.entity_id, ComparisonSentimentObservation.sentiment)
        .filter(ComparisonSentimentObservation.run_id == run_id, ComparisonSentimentObservation.entity_type == entity_type)
        .all()
    )
    return _counts_by_id(rows)


def _counts_by_id(rows: list[tuple[int, Sentiment]]) -> dict[int, tuple[int, int, int]]:
    out: dict[int, list[int]] = {}
    for entity_id, sentiment in rows:
        counts = out.setdefault(int(entity_id), [0, 0, 0])
        _inc(counts, sentiment)
    return {k: (v[0], v[1], v[2]) for k, v in out.items()}


def _inc(counts: list[int], sentiment: Sentiment) -> None:
    if sentiment == Sentiment.POSITIVE:
        counts[0] += 1
        return
    if sentiment == Sentiment.NEUTRAL:
        counts[1] += 1
        return
    counts[2] += 1


def _merge_counts(a: tuple[int, int, int] | None, b: tuple[int, int, int] | None) -> tuple[int, int, int]:
    a0, a1, a2 = a or (0, 0, 0)
    b0, b1, b2 = b or (0, 0, 0)
    return a0 + b0, a1 + b1, a2 + b2


def _sentiment_index(pos: int, neu: int, neg: int) -> float:
    total = max(0, int(pos) + int(neu) + int(neg))
    return float(pos) / float(total) if total else 0.0
