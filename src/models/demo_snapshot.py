from datetime import datetime

from pydantic import BaseModel, Field

from models.schemas import (
    AllRunMetricsResponse,
    AllRunProductMetricsResponse,
    BrandResponse,
    MetricsResponse,
    ProductMetricsResponse,
    RunResponse,
    VerticalResponse,
)


class DashboardModelSnapshot(BaseModel):
    model_name: str
    latest_run: RunResponse | None = None
    latest_brand_metrics: AllRunMetricsResponse | None = None
    latest_product_metrics: AllRunProductMetricsResponse | None = None
    aggregate_brand_metrics: MetricsResponse | None = None
    aggregate_product_metrics: ProductMetricsResponse | None = None


class DashboardVerticalSnapshot(BaseModel):
    vertical: VerticalResponse
    available_models: list[str] = Field(default_factory=list)
    user_brands: list[BrandResponse] = Field(default_factory=list)
    aggregate_brand_metrics: MetricsResponse | None = None
    aggregate_product_metrics: ProductMetricsResponse | None = None
    models: list[DashboardModelSnapshot] = Field(default_factory=list)


class DashboardSnapshot(BaseModel):
    version: str = "1"
    generated_at: datetime
    verticals: list[DashboardVerticalSnapshot] = Field(default_factory=list)
