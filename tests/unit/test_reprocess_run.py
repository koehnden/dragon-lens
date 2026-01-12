"""Unit tests for run reprocessing endpoint."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Run, RunStatus


def _create_run_id(client: TestClient) -> int:
    response = client.post(
        "/api/v1/tracking/jobs",
        json={"vertical_name": "SUV Cars", "brands": [{"display_name": "VW"}], "prompts": [{"text_en": "Test", "language_original": "en"}]},
    )
    return int(response.json()["run_id"])


def _set_run_status(db_session: Session, run_id: int, status: RunStatus) -> None:
    run = db_session.query(Run).filter(Run.id == run_id).first()
    run.status = status
    db_session.commit()


def test_reprocess_allows_pending(client: TestClient) -> None:
    run_id = _create_run_id(client)
    response = client.post(f"/api/v1/tracking/runs/{run_id}/reprocess")
    assert response.status_code == 200


def test_reprocess_allows_completed(client: TestClient, db_session: Session) -> None:
    run_id = _create_run_id(client)
    _set_run_status(db_session, run_id, RunStatus.COMPLETED)
    response = client.post(f"/api/v1/tracking/runs/{run_id}/reprocess")
    assert response.status_code == 200


def test_reprocess_allows_failed(client: TestClient, db_session: Session) -> None:
    run_id = _create_run_id(client)
    _set_run_status(db_session, run_id, RunStatus.FAILED)
    response = client.post(f"/api/v1/tracking/runs/{run_id}/reprocess")
    assert response.status_code == 200


def test_reprocess_rejects_in_progress(client: TestClient, db_session: Session) -> None:
    run_id = _create_run_id(client)
    _set_run_status(db_session, run_id, RunStatus.IN_PROGRESS)
    response = client.post(f"/api/v1/tracking/runs/{run_id}/reprocess")
    assert response.status_code == 409
