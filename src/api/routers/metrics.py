"""API router for metrics retrieval."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from models import Brand, BrandMention, DailyMetrics, LLMAnswer, Run, RunMetrics, Vertical, get_db
from models.schemas import AllRunMetricsResponse, BrandMetrics, MetricsResponse, RunMetricsResponse
from services.translater import format_entity_label

router = APIRouter()


def get_vertical_or_raise(db: Session, vertical_id: int) -> Vertical:
    vertical = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {vertical_id} not found")
    return vertical


def validate_brand_belongs_to_vertical(
    db: Session, brand_id: int, vertical_id: int
) -> Brand:
    brand = db.query(Brand).filter(Brand.id == brand_id).first()
    if not brand or brand.vertical_id != vertical_id:
        detail = f"Brand {brand_id} not found in vertical {vertical_id}"
        raise HTTPException(status_code=404, detail=detail)
    return brand


def validate_date_range(
    start_date: Optional[datetime], end_date: Optional[datetime]
) -> None:
    if start_date and end_date and start_date > end_date:
        detail = "start_date must be on or before end_date"
        raise HTTPException(status_code=400, detail=detail)


@router.get("/latest", response_model=MetricsResponse)
async def get_latest_metrics(
    vertical_id: int = Query(..., description="Vertical ID"),
    model_name: str = Query(..., description="Model name"),
    db: Session = Depends(get_db),
) -> MetricsResponse:
    """
    Get latest metrics for a vertical and model.

    Args:
        vertical_id: Vertical ID
        model_name: Model name
        db: Database session

    Returns:
        Latest metrics for all brands in the vertical

    Raises:
        HTTPException: If vertical not found or no data available
    """
    vertical = get_vertical_or_raise(db, vertical_id)

    latest_run = (
        db.query(Run)
        .filter(
            Run.vertical_id == vertical_id,
            Run.model_name == model_name,
            Run.answers.any(),
        )
        .order_by(Run.run_time.desc())
        .first()
    )

    if not latest_run:
        latest_run = (
            db.query(Run)
            .filter(
                Run.vertical_id == vertical_id,
                Run.model_name == model_name,
            )
            .order_by(Run.run_time.desc())
            .first()
        )

    if not latest_run:
        raise HTTPException(
            status_code=404,
            detail=f"No runs found for vertical {vertical_id} and model {model_name}",
        )

    brands = db.query(Brand).filter(Brand.vertical_id == vertical_id).all()

    brand_metrics = []
    for brand in brands:
        mentions = (
            db.query(BrandMention)
            .join(LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id)
            .filter(
                LLMAnswer.run_id == latest_run.id,
                BrandMention.brand_id == brand.id,
            )
            .all()
        )

        if not mentions:
            brand_metrics.append(
                BrandMetrics(
                    brand_id=brand.id,
                    brand_name=format_entity_label(brand.original_name, brand.translated_name),
                    mention_rate=0.0,
                    avg_rank=None,
                    sentiment_positive=0.0,
                    sentiment_neutral=0.0,
                    sentiment_negative=0.0,
                )
            )
            continue

        total_mentions = len(mentions)
        mentioned_count = sum(1 for m in mentions if m.mentioned)
        mention_rate = mentioned_count / total_mentions if total_mentions > 0 else 0.0

        ranks = [m.rank for m in mentions if m.mentioned and m.rank is not None]
        avg_rank = sum(ranks) / len(ranks) if ranks else None

        sentiment_counts = {"positive": 0, "neutral": 0, "negative": 0}
        for m in mentions:
            if m.mentioned:
                sentiment_counts[m.sentiment.value] += 1

        mentioned = mentioned_count if mentioned_count > 0 else 1
        sentiment_pos = sentiment_counts["positive"] / mentioned
        sentiment_neu = sentiment_counts["neutral"] / mentioned
        sentiment_neg = sentiment_counts["negative"] / mentioned

        brand_metrics.append(
            BrandMetrics(
                brand_id=brand.id,
                brand_name=format_entity_label(brand.original_name, brand.translated_name),
                mention_rate=mention_rate,
                avg_rank=avg_rank,
                sentiment_positive=sentiment_pos,
                sentiment_neutral=sentiment_neu,
                sentiment_negative=sentiment_neg,
            )
        )

    return MetricsResponse(
        vertical_id=vertical_id,
        vertical_name=vertical.name,
        model_name=model_name,
        date=latest_run.run_time,
        brands=brand_metrics,
    )


@router.get("/daily")
async def get_daily_metrics(
    vertical_id: int = Query(..., description="Vertical ID"),
    brand_id: int = Query(..., description="Brand ID"),
    model_name: str = Query(..., description="Model name"),
    start_date: Optional[datetime] = Query(None, description="Start date"),
    end_date: Optional[datetime] = Query(None, description="End date"),
    db: Session = Depends(get_db),
):
    """
    Get daily metrics for a specific brand over time.

    Args:
        vertical_id: Vertical ID
        brand_id: Brand ID
        model_name: Model name
        start_date: Start date (optional)
        end_date: End date (optional)
        db: Database session

    Returns:
        Daily metrics time series
    """
    get_vertical_or_raise(db, vertical_id)
    validate_brand_belongs_to_vertical(db, brand_id, vertical_id)
    validate_date_range(start_date, end_date)

    query = db.query(DailyMetrics).filter(
        DailyMetrics.vertical_id == vertical_id,
        DailyMetrics.brand_id == brand_id,
        DailyMetrics.model_name == model_name,
    )

    if start_date:
        query = query.filter(DailyMetrics.date >= start_date)
    if end_date:
        query = query.filter(DailyMetrics.date <= end_date)

    metrics = query.order_by(DailyMetrics.date).all()

    return {
        "vertical_id": vertical_id,
        "brand_id": brand_id,
        "model_name": model_name,
        "data": [
            {
                "date": m.date,
                "mention_rate": m.mention_rate,
                "avg_rank": m.avg_rank,
                "sentiment_positive": m.sentiment_pos,
                "sentiment_neutral": m.sentiment_neu,
                "sentiment_negative": m.sentiment_neg,
            }
            for m in metrics
        ],
    }


@router.get("/run/{run_id}", response_model=AllRunMetricsResponse)
async def get_run_metrics(
    run_id: int,
    db: Session = Depends(get_db),
) -> AllRunMetricsResponse:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    vertical = db.query(Vertical).filter(Vertical.id == run.vertical_id).first()
    if not vertical:
        raise HTTPException(status_code=404, detail=f"Vertical {run.vertical_id} not found")

    run_metrics = db.query(RunMetrics).filter(RunMetrics.run_id == run_id).all()

    metrics_responses = []
    for metric in run_metrics:
        brand = db.query(Brand).filter(Brand.id == metric.brand_id).first()
        if not brand:
            continue

        metrics_responses.append(
            RunMetricsResponse(
                brand_id=metric.brand_id,
                brand_name=format_entity_label(brand.original_name, brand.translated_name),
                is_user_input=brand.is_user_input,
                asov_coverage=metric.asov_coverage,
                asov_relative=metric.asov_relative,
                prominence_score=metric.prominence_score,
                top_spot_share=metric.top_spot_share,
                sentiment_index=metric.sentiment_index,
                positive_share=metric.positive_share,
                opportunity_rate=metric.opportunity_rate,
                dragon_visibility_score=metric.dragon_visibility_score,
            )
        )

    return AllRunMetricsResponse(
        run_id=run.id,
        vertical_id=run.vertical_id,
        vertical_name=vertical.name,
        model_name=run.model_name,
        run_time=run.run_time,
        metrics=metrics_responses,
    )
