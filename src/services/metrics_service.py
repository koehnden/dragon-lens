import logging
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from metrics.metrics import AnswerMetrics, visibility_metrics
from models import Brand, BrandMention, LLMAnswer, Prompt, Run, RunMetrics
from models.domain import BrandAlias, CanonicalBrand

logger = logging.getLogger(__name__)


def calculate_and_save_metrics(db: Session, run_id: int) -> None:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    vertical_id = run.vertical_id

    brands = db.query(Brand).filter(Brand.vertical_id == vertical_id).all()
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


def recalculate_metrics_with_canonical(db: Session, run_id: int) -> None:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")

    vertical_id = run.vertical_id

    canonical_brands = db.query(CanonicalBrand).filter(
        CanonicalBrand.vertical_id == vertical_id
    ).all()

    if not canonical_brands:
        logger.info(f"No canonical brands for vertical {vertical_id}, skipping")
        return

    brand_to_canonical = _build_brand_to_canonical_map(db, vertical_id)

    prompts = db.query(Prompt).filter(Prompt.run_id == run_id).all()
    if not prompts:
        return

    prompt_ids = [p.id for p in prompts]

    mentions = (
        db.query(BrandMention)
        .join(LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id)
        .all()
    )

    answer_metrics_list = _to_metrics_with_canonical(mentions, brand_to_canonical)

    canonical_names = [cb.canonical_name for cb in canonical_brands]

    for canonical_brand in canonical_brands:
        competitor_brands = [n for n in canonical_names if n != canonical_brand.canonical_name]

        metrics = visibility_metrics(
            prompt_ids=prompt_ids,
            mentions=answer_metrics_list,
            brand=canonical_brand.canonical_name,
            competitor_brands=competitor_brands,
        )

        logger.info(
            f"Canonical brand '{canonical_brand.canonical_name}': "
            f"mention_rate={metrics['mention_rate']:.2f}, "
            f"sov={metrics['share_of_voice']:.2f}"
        )

    db.commit()


def _build_brand_to_canonical_map(db: Session, vertical_id: int) -> Dict[str, str]:
    mapping: Dict[str, str] = {}

    canonical_brands = db.query(CanonicalBrand).filter(
        CanonicalBrand.vertical_id == vertical_id
    ).all()

    for canonical in canonical_brands:
        mapping[canonical.canonical_name.lower()] = canonical.canonical_name

        aliases = db.query(BrandAlias).filter(
            BrandAlias.canonical_brand_id == canonical.id
        ).all()

        for alias in aliases:
            mapping[alias.alias.lower()] = canonical.canonical_name

    return mapping


def _to_metrics_with_canonical(
    mentions: List[BrandMention],
    brand_to_canonical: Dict[str, str],
) -> List[AnswerMetrics]:
    metrics_list = []

    for mention in mentions:
        if not mention.mentioned:
            continue

        prompt_id = mention.llm_answer.prompt_id
        original_name = mention.brand.display_name
        canonical_name = brand_to_canonical.get(original_name.lower(), original_name)

        metrics_list.append(
            AnswerMetrics(
                prompt_id=prompt_id,
                brand=canonical_name,
                rank=mention.rank,
                sentiment=mention.sentiment.value,
            )
        )

    return metrics_list
