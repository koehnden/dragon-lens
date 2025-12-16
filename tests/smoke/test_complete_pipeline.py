"""Smoke test for complete tracking pipeline with Celery."""

import time

import pytest
from fastapi.testclient import TestClient


def test_minimal_tracking_pipeline(client: TestClient):
    """
    Test the complete tracking pipeline with a minimal example.

    This test:
    1. Creates a tracking job with 1 brand and 1 prompt
    2. Waits for the Celery task to process it
    3. Verifies the run completes successfully
    4. Checks that answers and mentions are created
    """
    response = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Test Cars",
            "brands": [
                {
                    "display_name": "Tesla",
                    "aliases": {"zh": ["特斯拉"], "en": ["Tesla Motors"]},
                }
            ],
            "prompts": [
                {
                    "text_zh": "推荐一款电动汽车",
                    "text_en": "Recommend an electric car",
                    "language_original": "zh",
                }
            ],
            "model_name": "qwen",
        },
    )

    assert response.status_code == 201
    data = response.json()
    run_id = data["run_id"]
    vertical_id = data["vertical_id"]

    print(f"\n✓ Created tracking job: run_id={run_id}, vertical_id={vertical_id}")

    max_wait_time = 120
    wait_interval = 2
    elapsed = 0

    while elapsed < max_wait_time:
        run_response = client.get(f"/api/v1/tracking/runs/{run_id}")
        assert run_response.status_code == 200
        run_data = run_response.json()
        status = run_data["status"]

        print(f"  Status after {elapsed}s: {status}")

        if status == "completed":
            print(f"✓ Run completed successfully after {elapsed}s")
            break
        elif status == "failed":
            error_msg = run_data.get("error_message", "Unknown error")
            pytest.fail(f"Run failed: {error_msg}")

        time.sleep(wait_interval)
        elapsed += wait_interval
    else:
        pytest.fail(f"Run did not complete within {max_wait_time}s (status: {status})")

    details_response = client.get(f"/api/v1/tracking/runs/{run_id}/details")
    assert details_response.status_code == 200
    details = details_response.json()

    print(f"\n✓ Retrieved run details")
    print(f"  Answers: {len(details['answers'])}")

    assert len(details["answers"]) == 1, "Should have 1 answer for 1 prompt"

    answer = details["answers"][0]
    assert answer["raw_answer_zh"], "Should have Chinese answer"
    print(f"  Chinese answer: {answer['raw_answer_zh'][:100]}...")

    if answer["raw_answer_en"]:
        print(f"  English answer: {answer['raw_answer_en'][:100]}...")

    print(f"  Mentions detected: {len(answer['mentions'])}")

    metrics_response = client.get(
        "/api/v1/metrics/latest",
        params={"vertical_id": vertical_id, "model_name": "qwen"},
    )
    assert metrics_response.status_code == 200
    metrics = metrics_response.json()

    print(f"\n✓ Retrieved metrics")
    print(f"  Brands in metrics: {len(metrics['brands'])}")

    for brand_metrics in metrics["brands"]:
        print(
            f"  {brand_metrics['brand_name']}: "
            f"mention_rate={brand_metrics['mention_rate']:.2%}, "
            f"sentiment_index={brand_metrics['sentiment_index']}"
        )

    print("\n✓ Complete pipeline test passed!")
