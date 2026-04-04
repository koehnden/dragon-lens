from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy.orm import Session

from models import Brand, Vertical
from models.demo_snapshot import (
    DashboardModelSnapshot,
    DashboardSnapshot,
    DashboardVerticalSnapshot,
)
from models.schemas import BrandResponse, VerticalResponse
from services.dashboard_metrics import (
    get_latest_brand_metrics,
    get_latest_completed_run,
    get_latest_product_metrics,
    get_run_brand_metrics,
    get_run_product_metrics,
    list_available_models,
)


def build_dashboard_snapshot(
    db: Session,
    vertical_ids: Iterable[int] | None = None,
    vertical_names: Iterable[str] | None = None,
) -> DashboardSnapshot:
    verticals = _selected_verticals(db, vertical_ids, vertical_names)
    return DashboardSnapshot(
        generated_at=datetime.now(timezone.utc),
        verticals=[_vertical_snapshot(db, vertical) for vertical in verticals],
    )


def _selected_verticals(
    db: Session,
    vertical_ids: Iterable[int] | None,
    vertical_names: Iterable[str] | None,
) -> list[Vertical]:
    if vertical_ids and vertical_names:
        raise ValueError("Use either vertical_ids or vertical_names, not both.")

    query = db.query(Vertical)
    if vertical_ids:
        query = query.filter(Vertical.id.in_(list(vertical_ids)))
    if vertical_names:
        query = query.filter(Vertical.name.in_(list(vertical_names)))
    return query.order_by(Vertical.name.asc()).all()


def _vertical_snapshot(db: Session, vertical: Vertical) -> DashboardVerticalSnapshot:
    available_models = list_available_models(db, vertical.id)
    return DashboardVerticalSnapshot(
        vertical=VerticalResponse.model_validate(vertical),
        available_models=available_models,
        user_brands=_user_brands(db, vertical.id),
        aggregate_brand_metrics=_safe_brand_metrics(db, vertical.id, "all"),
        aggregate_product_metrics=_safe_product_metrics(db, vertical.id, "all"),
        models=[
            _model_snapshot(db, vertical.id, model_name)
            for model_name in available_models
        ],
    )


def _user_brands(db: Session, vertical_id: int) -> list[BrandResponse]:
    brands = (
        db.query(Brand)
        .filter(Brand.vertical_id == vertical_id, Brand.is_user_input.is_(True))
        .order_by(Brand.id.asc())
        .all()
    )
    return [BrandResponse.model_validate(brand) for brand in brands]


def _model_snapshot(
    db: Session,
    vertical_id: int,
    model_name: str,
) -> DashboardModelSnapshot:
    latest_run = get_latest_completed_run(db, vertical_id, model_name)
    return DashboardModelSnapshot(
        model_name=model_name,
        latest_run=latest_run,
        latest_brand_metrics=None if latest_run is None else get_run_brand_metrics(db, latest_run.id),
        latest_product_metrics=None if latest_run is None else get_run_product_metrics(db, latest_run.id),
        aggregate_brand_metrics=_safe_brand_metrics(db, vertical_id, model_name),
        aggregate_product_metrics=_safe_product_metrics(db, vertical_id, model_name),
    )


def _safe_brand_metrics(
    db: Session,
    vertical_id: int,
    model_name: str,
):
    try:
        return get_latest_brand_metrics(db, vertical_id, model_name)
    except ValueError:
        return None


def _safe_product_metrics(
    db: Session,
    vertical_id: int,
    model_name: str,
):
    try:
        return get_latest_product_metrics(db, vertical_id, model_name)
    except ValueError:
        return None
