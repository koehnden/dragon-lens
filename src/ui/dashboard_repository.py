from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from config import settings
from models.demo_snapshot import DashboardSnapshot, DashboardVerticalSnapshot
from ui.utils.api import (
    fetch_available_models,
    fetch_json,
    fetch_user_brands,
    shorten_model_name,
)


class ApiDashboardRepository:
    def fetch_verticals(self) -> list[dict]:
        return fetch_json("/api/v1/verticals", timeout=10.0) or []

    def fetch_available_models(self, vertical_id: int) -> list[str]:
        return fetch_available_models(vertical_id)

    def fetch_user_brands(self, vertical_id: int) -> list[dict]:
        return fetch_user_brands(vertical_id)

    def fetch_aggregate_metrics(
        self,
        vertical_id: int,
        model_name: str,
        view_mode: str,
    ) -> dict | None:
        endpoint = "/api/v1/metrics/latest"
        if view_mode == "Product":
            endpoint = "/api/v1/metrics/latest/products"
        return fetch_json(
            endpoint,
            params={"vertical_id": vertical_id, "model_name": model_name},
        )

    def fetch_latest_run(self, vertical_id: int, model_name: str) -> dict | None:
        runs = fetch_json(
            "/api/v1/tracking/runs",
            params={"vertical_id": vertical_id, "model_name": model_name, "limit": 50},
            timeout=10.0,
        )
        if not runs:
            return None
        for run in runs:
            if run.get("status") == "completed":
                return run
        return None

    def fetch_run_metrics(self, run_id: int, view_mode: str) -> dict | None:
        if view_mode == "Brand":
            data = fetch_json(f"/api/v1/metrics/run/{run_id}")
            if not data:
                return None
            return {"brands": data.get("metrics") or []}
        return fetch_json(f"/api/v1/metrics/run/{run_id}/products")

    def fetch_per_model_metric_rows(
        self,
        vertical_id: int,
        models: list[str],
        view_mode: str,
    ) -> list[dict]:
        rows: list[dict] = []
        items_key = "products" if view_mode == "Product" else "brands"
        name_key = "product_name" if view_mode == "Product" else "brand_name"
        for model_name in models:
            data = self.fetch_aggregate_metrics(vertical_id, model_name, view_mode)
            if not data:
                continue
            for item in data.get(items_key) or []:
                rows.append(
                    {
                        "model": model_name,
                        "model_label": shorten_model_name(model_name),
                        "entity": item[name_key],
                        "sov": round(item["share_of_voice"] * 100),
                    }
                )
        return rows


class SnapshotDashboardRepository:
    def __init__(self, snapshot_path: str | Path):
        self.snapshot_path = Path(snapshot_path)
        self.snapshot = _load_snapshot(self.snapshot_path)

    def fetch_verticals(self) -> list[dict]:
        return [
            vertical.vertical.model_dump(mode="json")
            for vertical in self.snapshot.verticals
        ]

    def fetch_available_models(self, vertical_id: int) -> list[str]:
        vertical = self._vertical(vertical_id)
        return [] if vertical is None else vertical.available_models

    def fetch_user_brands(self, vertical_id: int) -> list[dict]:
        vertical = self._vertical(vertical_id)
        if vertical is None:
            return []
        return [brand.model_dump(mode="json") for brand in vertical.user_brands]

    def fetch_aggregate_metrics(
        self,
        vertical_id: int,
        model_name: str,
        view_mode: str,
    ) -> dict | None:
        vertical = self._vertical(vertical_id)
        if vertical is None:
            return None
        payload = self._aggregate_metrics(vertical, model_name, view_mode)
        return None if payload is None else payload.model_dump(mode="json")

    def fetch_latest_run(self, vertical_id: int, model_name: str) -> dict | None:
        model = self._model(vertical_id, model_name)
        if model is None or model.latest_run is None:
            return None
        return model.latest_run.model_dump(mode="json")

    def fetch_run_metrics(self, run_id: int, view_mode: str) -> dict | None:
        for vertical in self.snapshot.verticals:
            for model in vertical.models:
                if model.latest_run is None or model.latest_run.id != run_id:
                    continue
                payload = model.latest_brand_metrics if view_mode == "Brand" else model.latest_product_metrics
                if payload is None:
                    return None
                if view_mode == "Brand":
                    return {"brands": [metric.model_dump(mode="json") for metric in payload.metrics]}
                return payload.model_dump(mode="json")
        return None

    def fetch_per_model_metric_rows(
        self,
        vertical_id: int,
        models: list[str],
        view_mode: str,
    ) -> list[dict]:
        rows: list[dict] = []
        items_key = "products" if view_mode == "Product" else "brands"
        name_key = "product_name" if view_mode == "Product" else "brand_name"
        for model_name in models:
            payload = self.fetch_aggregate_metrics(vertical_id, model_name, view_mode)
            if not payload:
                continue
            for item in payload.get(items_key) or []:
                rows.append(
                    {
                        "model": model_name,
                        "model_label": shorten_model_name(model_name),
                        "entity": item[name_key],
                        "sov": round(item["share_of_voice"] * 100),
                    }
                )
        return rows

    def _vertical(self, vertical_id: int) -> DashboardVerticalSnapshot | None:
        for vertical in self.snapshot.verticals:
            if vertical.vertical.id == vertical_id:
                return vertical
        return None

    def _model(self, vertical_id: int, model_name: str):
        vertical = self._vertical(vertical_id)
        if vertical is None:
            return None
        for model in vertical.models:
            if model.model_name == model_name:
                return model
        return None

    def _aggregate_metrics(
        self,
        vertical: DashboardVerticalSnapshot,
        model_name: str,
        view_mode: str,
    ):
        if model_name == "all":
            return (
                vertical.aggregate_brand_metrics
                if view_mode == "Brand"
                else vertical.aggregate_product_metrics
            )
        model = self._model(vertical.vertical.id, model_name)
        if model is None:
            return None
        return (
            model.aggregate_brand_metrics
            if view_mode == "Brand"
            else model.aggregate_product_metrics
        )


def get_dashboard_repository() -> ApiDashboardRepository | SnapshotDashboardRepository:
    if settings.is_public_demo:
        return SnapshotDashboardRepository(settings.dashboard_snapshot_path)
    return ApiDashboardRepository()


def _load_snapshot(snapshot_path: Path) -> DashboardSnapshot:
    if not snapshot_path.exists():
        return _empty_snapshot()
    try:
        return DashboardSnapshot.model_validate_json(snapshot_path.read_text(encoding="utf-8"))
    except (OSError, ValidationError):
        return _empty_snapshot()


def _empty_snapshot() -> DashboardSnapshot:
    return DashboardSnapshot(
        generated_at=datetime.now(timezone.utc),
        verticals=[],
    )
