import logging
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.domain import (
    Brand,
    EntityType,
    Feature,
    FeatureMention,
    Product,
    RunFeatureMetrics,
    Sentiment,
)

logger = logging.getLogger(__name__)


@dataclass
class FeatureScore:
    feature_id: int
    feature_name_zh: str
    feature_name_en: Optional[str]
    frequency: int
    positive_count: int
    neutral_count: int
    negative_count: int
    combined_score: float


@dataclass
class EntityFeatureData:
    entity_id: int
    entity_name: str
    entity_type: str
    features: list[FeatureScore] = field(default_factory=list)


@dataclass
class SpiderChartData:
    run_id: int
    vertical_id: int
    vertical_name: str
    top_features: list[str]
    entities: list[EntityFeatureData]


def calculate_combined_score(
    frequency: int,
    positive_count: int,
    neutral_count: int,
    negative_count: int,
) -> float:
    total = positive_count + neutral_count + negative_count
    if total == 0:
        return 0.0

    sentiment_weight = (positive_count - negative_count) / total
    normalized_sentiment = (sentiment_weight + 1) / 2
    return frequency * normalized_sentiment


def calculate_feature_metrics_for_run(
    db: Session,
    run_id: int,
    vertical_id: int,
) -> None:
    stmt = (
        select(
            FeatureMention.feature_id,
            func.coalesce(FeatureMention.brand_mention_id, 0).label("entity_id_raw"),
            func.count().label("frequency"),
            func.sum(
                func.case((FeatureMention.sentiment == Sentiment.POSITIVE, 1), else_=0)
            ).label("positive_count"),
            func.sum(
                func.case((FeatureMention.sentiment == Sentiment.NEUTRAL, 1), else_=0)
            ).label("neutral_count"),
            func.sum(
                func.case((FeatureMention.sentiment == Sentiment.NEGATIVE, 1), else_=0)
            ).label("negative_count"),
        )
        .where(FeatureMention.brand_mention_id.isnot(None))
        .group_by(FeatureMention.feature_id, FeatureMention.brand_mention_id)
    )

    results = db.execute(stmt).all()

    for row in results:
        combined = calculate_combined_score(
            row.frequency, row.positive_count, row.neutral_count, row.negative_count
        )
        metrics = RunFeatureMetrics(
            run_id=run_id,
            entity_type=EntityType.BRAND,
            entity_id=row.entity_id_raw,
            feature_id=row.feature_id,
            frequency=row.frequency,
            positive_count=row.positive_count,
            neutral_count=row.neutral_count,
            negative_count=row.negative_count,
            combined_score=combined,
        )
        db.add(metrics)

    db.commit()


def get_top_features_for_entities(
    db: Session,
    run_id: int,
    entity_ids: list[int],
    entity_type: EntityType,
    top_n: int = 6,
) -> list[Feature]:
    stmt = (
        select(
            RunFeatureMetrics.feature_id,
            func.sum(RunFeatureMetrics.frequency).label("total_freq"),
        )
        .where(
            RunFeatureMetrics.run_id == run_id,
            RunFeatureMetrics.entity_type == entity_type,
            RunFeatureMetrics.entity_id.in_(entity_ids),
        )
        .group_by(RunFeatureMetrics.feature_id)
        .order_by(func.sum(RunFeatureMetrics.frequency).desc())
        .limit(top_n)
    )

    results = db.execute(stmt).all()
    feature_ids = [row.feature_id for row in results]

    if not feature_ids:
        return []

    features = db.execute(
        select(Feature).where(Feature.id.in_(feature_ids))
    ).scalars().all()

    feature_map = {f.id: f for f in features}
    return [feature_map[fid] for fid in feature_ids if fid in feature_map]


def get_spider_chart_data(
    db: Session,
    run_id: int,
    entity_ids: list[int],
    entity_type: EntityType,
    top_n: int = 6,
) -> Optional[SpiderChartData]:
    from models.domain import Run, Vertical

    run = db.execute(select(Run).where(Run.id == run_id)).scalar_one_or_none()
    if not run:
        return None

    vertical = db.execute(
        select(Vertical).where(Vertical.id == run.vertical_id)
    ).scalar_one_or_none()
    if not vertical:
        return None

    top_features = get_top_features_for_entities(
        db, run_id, entity_ids, entity_type, top_n
    )

    if not top_features:
        return SpiderChartData(
            run_id=run_id,
            vertical_id=vertical.id,
            vertical_name=vertical.name,
            top_features=[],
            entities=[],
        )

    feature_ids = [f.id for f in top_features]
    feature_names = [f.display_name_zh for f in top_features]

    entities_data = []
    for entity_id in entity_ids:
        entity_name = _get_entity_name(db, entity_id, entity_type)

        stmt = select(RunFeatureMetrics).where(
            RunFeatureMetrics.run_id == run_id,
            RunFeatureMetrics.entity_type == entity_type,
            RunFeatureMetrics.entity_id == entity_id,
            RunFeatureMetrics.feature_id.in_(feature_ids),
        )
        metrics = db.execute(stmt).scalars().all()

        metrics_by_feature = {m.feature_id: m for m in metrics}

        feature_scores = []
        for feature in top_features:
            m = metrics_by_feature.get(feature.id)
            if m:
                feature_scores.append(FeatureScore(
                    feature_id=feature.id,
                    feature_name_zh=feature.display_name_zh,
                    feature_name_en=feature.display_name_en,
                    frequency=m.frequency,
                    positive_count=m.positive_count,
                    neutral_count=m.neutral_count,
                    negative_count=m.negative_count,
                    combined_score=m.combined_score,
                ))
            else:
                feature_scores.append(FeatureScore(
                    feature_id=feature.id,
                    feature_name_zh=feature.display_name_zh,
                    feature_name_en=feature.display_name_en,
                    frequency=0,
                    positive_count=0,
                    neutral_count=0,
                    negative_count=0,
                    combined_score=0.0,
                ))

        entities_data.append(EntityFeatureData(
            entity_id=entity_id,
            entity_name=entity_name,
            entity_type=entity_type.value,
            features=feature_scores,
        ))

    return SpiderChartData(
        run_id=run_id,
        vertical_id=vertical.id,
        vertical_name=vertical.name,
        top_features=feature_names,
        entities=entities_data,
    )


def _get_entity_name(db: Session, entity_id: int, entity_type: EntityType) -> str:
    if entity_type == EntityType.BRAND:
        brand = db.execute(
            select(Brand).where(Brand.id == entity_id)
        ).scalar_one_or_none()
        return brand.display_name if brand else f"Brand {entity_id}"
    else:
        product = db.execute(
            select(Product).where(Product.id == entity_id)
        ).scalar_one_or_none()
        return product.display_name if product else f"Product {entity_id}"
