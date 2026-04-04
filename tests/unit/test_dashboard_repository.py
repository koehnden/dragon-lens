from datetime import datetime, timezone

from models.demo_snapshot import (
    DashboardModelSnapshot,
    DashboardSnapshot,
    DashboardVerticalSnapshot,
)
from models.schemas import (
    AllRunMetricsResponse,
    AllRunProductMetricsResponse,
    BrandMetrics,
    BrandResponse,
    MetricsResponse,
    ProductMetrics,
    ProductMetricsResponse,
    RunMetricsResponse,
    RunResponse,
    VerticalResponse,
)
from ui.dashboard_repository import SnapshotDashboardRepository


def test_snapshot_dashboard_repository_reads_public_demo_snapshot(tmp_path) -> None:
    snapshot_path = tmp_path / "dashboard_snapshot.json"
    snapshot_path.write_text(_snapshot_fixture().model_dump_json(indent=2), encoding="utf-8")

    repository = SnapshotDashboardRepository(snapshot_path)

    assert repository.fetch_verticals() == [
        {
            "id": 7,
            "name": "SUV Cars",
            "description": "Sport Utility Vehicles",
            "created_at": "2026-04-02T00:00:00Z",
        }
    ]
    assert repository.fetch_available_models(7) == [
        "qwen/qwen-2.5-72b-instruct",
        "deepseek-chat",
    ]
    assert [brand["display_name"] for brand in repository.fetch_user_brands(7)] == ["Toyota"]
    assert repository.fetch_aggregate_metrics(7, "all", "Brand")["model_name"] == "All Models"
    assert repository.fetch_aggregate_metrics(7, "deepseek-chat", "Product")["model_name"] == "deepseek-chat"
    assert repository.fetch_latest_run(7, "deepseek-chat")["id"] == 102
    assert repository.fetch_run_metrics(102, "Brand")["metrics"][0]["brand_name"] == "Toyota"

    heatmap_rows = repository.fetch_per_model_metric_rows(
        7,
        ["qwen/qwen-2.5-72b-instruct", "deepseek-chat"],
        "Brand",
    )
    assert heatmap_rows == [
        {"model": "Qwen 72B", "entity": "Toyota", "sov": 58},
        {"model": "DeepSeek V3.2", "entity": "Toyota", "sov": 61},
    ]


def _snapshot_fixture() -> DashboardSnapshot:
    created_at = datetime(2026, 4, 2, tzinfo=timezone.utc)
    vertical = VerticalResponse(
        id=7,
        name="SUV Cars",
        description="Sport Utility Vehicles",
        created_at=created_at,
    )
    user_brand = BrandResponse(
        id=1,
        vertical_id=7,
        display_name="Toyota",
        original_name="Toyota",
        translated_name=None,
        aliases={"en": ["Toyota"], "zh": ["丰田"]},
        is_user_input=True,
        created_at=created_at,
    )
    aggregate_brand_metrics = MetricsResponse(
        vertical_id=7,
        vertical_name="SUV Cars",
        model_name="All Models",
        date=created_at,
        brands=[
            BrandMetrics(
                brand_id=1,
                brand_name="Toyota",
                mention_rate=1.0,
                share_of_voice=0.6,
                top_spot_share=0.5,
                sentiment_index=0.8,
                dragon_lens_visibility=0.7,
            )
        ],
    )
    aggregate_product_metrics = ProductMetricsResponse(
        vertical_id=7,
        vertical_name="SUV Cars",
        model_name="All Models",
        date=created_at,
        products=[
            ProductMetrics(
                product_id=11,
                product_name="RAV4",
                brand_id=1,
                brand_name="Toyota",
                mention_rate=1.0,
                share_of_voice=0.6,
                top_spot_share=0.5,
                sentiment_index=0.8,
                dragon_lens_visibility=0.7,
            )
        ],
    )
    qwen_run = RunResponse(
        id=101,
        vertical_id=7,
        provider="openrouter",
        model_name="qwen/qwen-2.5-72b-instruct",
        route=None,
        status="completed",
        run_time=created_at,
        completed_at=created_at,
        error_message=None,
    )
    deepseek_run = RunResponse(
        id=102,
        vertical_id=7,
        provider="deepseek",
        model_name="deepseek-chat",
        route=None,
        status="completed",
        run_time=created_at,
        completed_at=created_at,
        error_message=None,
    )
    qwen_brand_metrics = MetricsResponse(
        vertical_id=7,
        vertical_name="SUV Cars",
        model_name="qwen/qwen-2.5-72b-instruct",
        date=created_at,
        brands=[
            BrandMetrics(
                brand_id=1,
                brand_name="Toyota",
                mention_rate=1.0,
                share_of_voice=0.58,
                top_spot_share=0.6,
                sentiment_index=0.8,
                dragon_lens_visibility=0.72,
            )
        ],
    )
    deepseek_product_metrics = ProductMetricsResponse(
        vertical_id=7,
        vertical_name="SUV Cars",
        model_name="deepseek-chat",
        date=created_at,
        products=[
            ProductMetrics(
                product_id=11,
                product_name="RAV4",
                brand_id=1,
                brand_name="Toyota",
                mention_rate=1.0,
                share_of_voice=0.61,
                top_spot_share=0.6,
                sentiment_index=0.8,
                dragon_lens_visibility=0.75,
            )
        ],
    )
    deepseek_run_brand_metrics = AllRunMetricsResponse(
        run_id=102,
        vertical_id=7,
        vertical_name="SUV Cars",
        provider="deepseek",
        model_name="deepseek-chat",
        run_time=created_at,
        metrics=[
            RunMetricsResponse(
                brand_id=1,
                brand_name="Toyota",
                is_user_input=True,
                top_spot_share=1.0,
                sentiment_index=1.0,
                mention_rate=1.0,
                share_of_voice=0.7,
                dragon_lens_visibility=0.85,
            )
        ],
    )
    deepseek_run_product_metrics = AllRunProductMetricsResponse(
        run_id=102,
        vertical_id=7,
        vertical_name="SUV Cars",
        provider="deepseek",
        model_name="deepseek-chat",
        run_time=created_at,
        products=[
            ProductMetrics(
                product_id=11,
                product_name="RAV4",
                brand_id=1,
                brand_name="Toyota",
                mention_rate=1.0,
                share_of_voice=0.7,
                top_spot_share=1.0,
                sentiment_index=1.0,
                dragon_lens_visibility=0.85,
            )
        ],
    )

    return DashboardSnapshot(
        generated_at=created_at,
        verticals=[
            DashboardVerticalSnapshot(
                vertical=vertical,
                available_models=["qwen/qwen-2.5-72b-instruct", "deepseek-chat"],
                user_brands=[user_brand],
                aggregate_brand_metrics=aggregate_brand_metrics,
                aggregate_product_metrics=aggregate_product_metrics,
                models=[
                    DashboardModelSnapshot(
                        model_name="qwen/qwen-2.5-72b-instruct",
                        latest_run=qwen_run,
                        latest_brand_metrics=None,
                        latest_product_metrics=None,
                        aggregate_brand_metrics=qwen_brand_metrics,
                        aggregate_product_metrics=None,
                    ),
                    DashboardModelSnapshot(
                        model_name="deepseek-chat",
                        latest_run=deepseek_run,
                        latest_brand_metrics=deepseek_run_brand_metrics,
                        latest_product_metrics=deepseek_run_product_metrics,
                        aggregate_brand_metrics=MetricsResponse(
                            vertical_id=7,
                            vertical_name="SUV Cars",
                            model_name="deepseek-chat",
                            date=created_at,
                            brands=[
                                BrandMetrics(
                                    brand_id=1,
                                    brand_name="Toyota",
                                    mention_rate=1.0,
                                    share_of_voice=0.61,
                                    top_spot_share=0.6,
                                    sentiment_index=0.8,
                                    dragon_lens_visibility=0.75,
                                )
                            ],
                        ),
                        aggregate_product_metrics=deepseek_product_metrics,
                    ),
                ],
            )
        ],
    )
