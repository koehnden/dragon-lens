"""Smoke tests for DragonLens API endpoints.

Smoke tests verify that all API endpoints are accessible and return expected status codes.
They run through a logical workflow from vertical creation to metrics retrieval.
"""

import time
import pytest
from fastapi.testclient import TestClient


def test_api_smoke_workflow(client: TestClient, db_session):
    """
    Complete smoke test workflow running all endpoints in logical order.

    Workflow:
    1. Create Vertical (SUV)
    2. List Verticals → verify new vertical is present
    3. Get Vertical → verify details
    4. Create Tracking Job
    5. List Runs → verify new run is present
    6. Get Run → poll until completed (or verify pending)
    7. Get Latest Metrics
    8. Get Daily Metrics
    """

    # Step 1: Create Vertical
    print("\n[SMOKE] Step 1: Creating vertical...")
    vertical_response = client.post(
        "/api/v1/verticals",
        json={
            "name": "SUV Cars - Smoke Test",
            "description": "Sport utility vehicles for smoke testing",
        },
    )
    assert vertical_response.status_code == 201, f"Create Vertical failed: {vertical_response.text}"
    vertical_data = vertical_response.json()
    vertical_id = vertical_data["id"]
    print(f"[SMOKE] ✓ Vertical created with ID: {vertical_id}")

    # Verify response structure
    assert "id" in vertical_data
    assert vertical_data["name"] == "SUV Cars - Smoke Test"
    assert vertical_data["description"] == "Sport utility vehicles for smoke testing"
    assert "created_at" in vertical_data

    # Step 2: List Verticals
    print("[SMOKE] Step 2: Listing verticals...")
    list_response = client.get("/api/v1/verticals")
    assert list_response.status_code == 200, f"List Verticals failed: {list_response.text}"
    verticals = list_response.json()
    print(f"[SMOKE] ✓ Found {len(verticals)} vertical(s)")

    # Verify our vertical is in the list
    vertical_ids = [v["id"] for v in verticals]
    assert vertical_id in vertical_ids, f"Created vertical {vertical_id} not found in list"
    print(f"[SMOKE] ✓ Created vertical present in list")

    # Step 3: Get Vertical by ID
    print(f"[SMOKE] Step 3: Getting vertical {vertical_id}...")
    get_response = client.get(f"/api/v1/verticals/{vertical_id}")
    assert get_response.status_code == 200, f"Get Vertical failed: {get_response.text}"
    vertical_detail = get_response.json()
    print(f"[SMOKE] ✓ Retrieved vertical: {vertical_detail['name']}")

    # Verify details match
    assert vertical_detail["id"] == vertical_id
    assert vertical_detail["name"] == "SUV Cars - Smoke Test"

    # Step 4: Create Tracking Job
    print("[SMOKE] Step 4: Creating tracking job...")
    job_response = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "SUV Cars - Smoke Test",
            "vertical_description": "Sport utility vehicles for smoke testing",
            "brands": [
                {
                    "display_name": "Toyota",
                    "aliases": {"zh": ["丰田"], "en": ["Toyota Motors"]},
                },
                {
                    "display_name": "Honda",
                    "aliases": {"zh": ["本田"], "en": []},
                },
            ],
            "prompts": [
                {
                    "text_en": "What are the best SUV brands?",
                    "text_zh": "最好的SUV品牌是什么？",
                    "language_original": "en",
                },
                {
                    "text_en": "Recommend a reliable SUV",
                    "text_zh": "推荐一款可靠的SUV",
                    "language_original": "en",
                },
            ],
            "model_name": "qwen",
        },
    )
    assert job_response.status_code == 201, f"Create Tracking Job failed: {job_response.text}"
    job_data = job_response.json()
    run_id = job_data["run_id"]
    print(f"[SMOKE] ✓ Tracking job created with run ID: {run_id}")

    # Verify job response structure
    assert job_data["vertical_id"] == vertical_id
    assert job_data["model_name"] == "qwen"
    assert job_data["status"] == "pending"
    assert "message" in job_data

    # Step 5: List Runs
    print("[SMOKE] Step 5: Listing runs...")
    runs_response = client.get("/api/v1/tracking/runs")
    assert runs_response.status_code == 200, f"List Runs failed: {runs_response.text}"
    runs = runs_response.json()
    print(f"[SMOKE] ✓ Found {len(runs)} run(s)")

    # Verify our run is in the list
    run_ids = [r["id"] for r in runs]
    assert run_id in run_ids, f"Created run {run_id} not found in list"
    print(f"[SMOKE] ✓ Created run present in list")

    # Filter runs by vertical
    filtered_runs_response = client.get(f"/api/v1/tracking/runs?vertical_id={vertical_id}")
    assert filtered_runs_response.status_code == 200
    filtered_runs = filtered_runs_response.json()
    print(f"[SMOKE] ✓ Found {len(filtered_runs)} run(s) for vertical {vertical_id}")
    assert len(filtered_runs) >= 1

    # Step 6: Get Run Details (with polling simulation)
    print(f"[SMOKE] Step 6: Getting run {run_id} details...")
    run_response = client.get(f"/api/v1/tracking/runs/{run_id}")
    assert run_response.status_code == 200, f"Get Run failed: {run_response.text}"
    run_detail = run_response.json()
    print(f"[SMOKE] ✓ Run status: {run_detail['status']}")

    # Verify run details
    assert run_detail["id"] == run_id
    assert run_detail["vertical_id"] == vertical_id
    assert run_detail["model_name"] == "qwen"
    assert run_detail["status"] in ["pending", "in_progress", "completed", "failed"]
    assert "run_time" in run_detail

    # Simulate polling (in smoke test, we don't actually wait for completion)
    # In a real scenario, this would poll until status is "completed"
    max_polls = 3
    poll_count = 0
    while poll_count < max_polls and run_detail["status"] == "pending":
        print(f"[SMOKE] Polling run status (attempt {poll_count + 1}/{max_polls})...")
        time.sleep(0.1)  # Short sleep for smoke test
        run_response = client.get(f"/api/v1/tracking/runs/{run_id}")
        run_detail = run_response.json()
        poll_count += 1

    print(f"[SMOKE] ✓ Final run status after polling: {run_detail['status']}")

    # Step 7: Get Latest Metrics
    print("[SMOKE] Step 7: Getting latest metrics...")
    metrics_response = client.get(
        f"/api/v1/metrics/latest?vertical_id={vertical_id}&model_name=qwen"
    )

    # Metrics might not be available if run is still pending (expected in smoke test)
    if run_detail["status"] == "completed":
        assert metrics_response.status_code == 200, f"Get Latest Metrics failed: {metrics_response.text}"
        metrics_data = metrics_response.json()
        print(f"[SMOKE] ✓ Retrieved metrics for {len(metrics_data['brands'])} brand(s)")

        # Verify metrics structure
        assert metrics_data["vertical_id"] == vertical_id
        assert metrics_data["model_name"] == "qwen"
        assert "brands" in metrics_data
        assert len(metrics_data["brands"]) == 2  # Toyota and Honda
    else:
        # For pending/in_progress runs, we expect 404 (no metrics yet) or metrics with 0 values
        print(f"[SMOKE] ℹ Run not completed, skipping metrics validation (got {metrics_response.status_code})")
        # This is acceptable for smoke test - we verified the endpoint is accessible
        assert metrics_response.status_code in [200, 404]

    # Step 8: Get Daily Metrics
    print("[SMOKE] Step 8: Getting daily metrics...")
    # Get the brand IDs from database to test daily metrics
    from src.models import Brand
    brands = db_session.query(Brand).filter(Brand.vertical_id == vertical_id).all()

    if brands:
        brand_id = brands[0].id
        daily_response = client.get(
            f"/api/v1/metrics/daily?vertical_id={vertical_id}&brand_id={brand_id}&model_name=qwen"
        )
        assert daily_response.status_code == 200, f"Get Daily Metrics failed: {daily_response.text}"
        daily_data = daily_response.json()
        print(f"[SMOKE] ✓ Retrieved daily metrics: {len(daily_data['data'])} data point(s)")

        # Verify daily metrics structure
        assert daily_data["vertical_id"] == vertical_id
        assert daily_data["brand_id"] == brand_id
        assert daily_data["model_name"] == "qwen"
        assert "data" in daily_data
        # Data might be empty for new run (expected)
    else:
        print("[SMOKE] ℹ No brands found, skipping daily metrics test")

    print("\n[SMOKE] ✅ All smoke tests passed!")
    print(f"[SMOKE] Summary:")
    print(f"  - Vertical ID: {vertical_id}")
    print(f"  - Run ID: {run_id}")
    print(f"  - Run Status: {run_detail['status']}")
    print(f"  - All endpoints responded with expected status codes")


def test_health_endpoints_smoke(client: TestClient):
    """Smoke test for health and root endpoints."""

    print("\n[SMOKE] Testing health endpoints...")

    # Test root endpoint
    root_response = client.get("/")
    assert root_response.status_code == 200
    root_data = root_response.json()
    assert root_data["name"] == "DragonLens"
    assert root_data["version"] == "0.1.0"
    assert root_data["status"] == "running"
    print("[SMOKE] ✓ Root endpoint accessible")

    # Test health endpoint
    health_response = client.get("/health")
    assert health_response.status_code == 200
    health_data = health_response.json()
    assert health_data["status"] == "healthy"
    print("[SMOKE] ✓ Health endpoint accessible")

    print("[SMOKE] ✅ Health endpoints smoke test passed!")


def test_error_handling_smoke(client: TestClient):
    """Smoke test for error handling."""

    print("\n[SMOKE] Testing error handling...")

    # Test 404 for non-existent vertical
    response = client.get("/api/v1/verticals/999999")
    assert response.status_code == 404
    print("[SMOKE] ✓ 404 returned for non-existent vertical")

    # Test 404 for non-existent run
    response = client.get("/api/v1/tracking/runs/999999")
    assert response.status_code == 404
    print("[SMOKE] ✓ 404 returned for non-existent run")

    # Test 404 for non-existent metrics
    response = client.get("/api/v1/metrics/latest?vertical_id=999999&model_name=qwen")
    assert response.status_code == 404
    print("[SMOKE] ✓ 404 returned for non-existent metrics")

    # Test 400 for duplicate vertical
    client.post("/api/v1/verticals", json={"name": "Duplicate Test Vertical"})
    response = client.post("/api/v1/verticals", json={"name": "Duplicate Test Vertical"})
    assert response.status_code == 400
    print("[SMOKE] ✓ 400 returned for duplicate vertical")

    print("[SMOKE] ✅ Error handling smoke test passed!")
