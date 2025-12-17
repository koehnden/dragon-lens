"""API router for metrics retrieval."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from models import (
    Brand,
    BrandMention,
    DailyMetrics,
    LLMAnswer,
    Prompt,
    Run,
    RunMetrics,
    Vertical,
    get_db,
)
from metrics.metrics import AnswerMetrics, visibility_metrics
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

    prompts = db.query(Prompt).filter(Prompt.vertical_id == vertical_id).all()
    prompt_ids = [p.id for p in prompts]
    brands = db.query(Brand).filter(Brand.vertical_id == vertical_id).all()
    mentions = (
        db.query(BrandMention)
        .join(LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id)
        .filter(LLMAnswer.run_id == latest_run.id)
        .all()
    )
    answer_metrics = [
        AnswerMetrics(
            prompt_id=m.llm_answer.prompt_id,
            brand=m.brand.display_name,
            rank=m.rank,
            sentiment=m.sentiment.value,
        )
        for m in mentions
        if m.mentioned
    ]

    brand_metrics = []
    brand_names = [b.display_name for b in brands]
    for brand in brands:
        competitors = [name for name in brand_names if name != brand.display_name]
        metrics = visibility_metrics(
            prompt_ids=prompt_ids,
            mentions=answer_metrics,
            brand=brand.display_name,
            competitor_brands=competitors,
        )

        brand_metrics.append(
            BrandMetrics(
                brand_id=brand.id,
                brand_name=format_entity_label(brand.original_name, brand.translated_name),
                entity_type=brand.entity_type.value if brand.entity_type else "unknown",
                mention_rate=metrics["mention_rate"],
                share_of_voice=metrics["share_of_voice"],
                top_spot_share=metrics["top_spot_share"],
                sentiment_index=metrics["sentiment_index"],
                dragon_lens_visibility=metrics["dragon_lens_visibility"],
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
                "share_of_voice": m.share_of_voice,
                "top_spot_share": m.top_spot_share,
                "sentiment_index": m.sentiment_index,
                "dragon_lens_visibility": m.dragon_lens_visibility,
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
                entity_type=brand.entity_type.value if brand.entity_type else "unknown",
                is_user_input=brand.is_user_input,
                top_spot_share=metric.top_spot_share,
                sentiment_index=metric.sentiment_index,
                mention_rate=metric.mention_rate,
                share_of_voice=metric.share_of_voice,
                dragon_lens_visibility=metric.dragon_lens_visibility,
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
