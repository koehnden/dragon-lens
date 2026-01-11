from fastapi.testclient import TestClient

from models import ComparisonPrompt, RunComparisonConfig


def test_create_tracking_job_persists_comparison_config_by_default(client: TestClient, db_session):
    response = client.post(
        "/api/v1/tracking/jobs",
        json={
            "vertical_name": "Shoes",
            "brands": [{"display_name": "Salomon"}],
            "prompts": [{"text_en": "Recommend hiking shoes", "language_original": "en"}],
        },
    )
    assert response.status_code == 201
    run_id = response.json()["run_id"]
    config = db_session.query(RunComparisonConfig).filter(RunComparisonConfig.run_id == run_id).first()
    assert config and config.enabled
    prompts = db_session.query(ComparisonPrompt).filter(ComparisonPrompt.run_id == run_id).all()
    assert len(prompts) == 0
