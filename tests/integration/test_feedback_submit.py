import json

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Run, RunStatus, Vertical
from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeFeedbackEvent,
    KnowledgeProduct,
    KnowledgeProductBrandMapping,
    KnowledgeRejectedEntity,
    KnowledgeTranslationOverride,
    KnowledgeVertical,
    KnowledgeVerticalAlias,
)


def test_feedback_submit_persists_entries(
    client: TestClient,
    db_session: Session,
    knowledge_db_session: Session,
):
    vertical = Vertical(name="SUV Cars", description="SUV segment")
    db_session.add(vertical)
    db_session.commit()

    run = Run(vertical_id=vertical.id, model_name="qwen", status=RunStatus.COMPLETED)
    db_session.add(run)
    db_session.commit()

    payload = {
        "run_id": run.id,
        "vertical_id": vertical.id,
        "canonical_vertical": {"is_new": True, "name": "Cars"},
        "brand_feedback": [
            {
                "action": "replace",
                "wrong_name": "四驱",
                "correct_name": "丰田",
                "reason": "generic term",
            }
        ],
        "product_feedback": [{"action": "validate", "name": "RAV4"}],
        "mapping_feedback": [{"action": "add", "product_name": "RAV4", "brand_name": "丰田"}],
        "translation_overrides": [
            {
                "entity_type": "brand",
                "canonical_name": "丰田",
                "language": "en",
                "override_text": "Toyota",
            }
        ],
    }

    response = client.post("/api/v1/feedback/submit", json=payload)

    assert response.status_code == 200
    data = response.json()

    assert data["run_id"] == run.id
    assert data["applied"]["brands"] == 1
    assert data["applied"]["products"] == 1
    assert data["applied"]["mappings"] == 1
    assert data["applied"]["translations"] == 1

    vertical_row = knowledge_db_session.query(KnowledgeVertical).filter(
        KnowledgeVertical.name == "Cars"
    ).first()
    assert vertical_row is not None

    alias_row = knowledge_db_session.query(KnowledgeVerticalAlias).filter(
        KnowledgeVerticalAlias.vertical_id == vertical_row.id,
        KnowledgeVerticalAlias.alias == "SUV Cars",
    ).first()
    assert alias_row is not None

    brand = knowledge_db_session.query(KnowledgeBrand).filter(
        KnowledgeBrand.vertical_id == vertical_row.id,
        KnowledgeBrand.canonical_name == "丰田",
    ).first()
    assert brand is not None
    assert brand.is_validated is True

    rejected = knowledge_db_session.query(KnowledgeRejectedEntity).filter(
        KnowledgeRejectedEntity.vertical_id == vertical_row.id,
        KnowledgeRejectedEntity.name == "四驱",
    ).first()
    assert rejected is not None

    product = knowledge_db_session.query(KnowledgeProduct).filter(
        KnowledgeProduct.vertical_id == vertical_row.id,
        KnowledgeProduct.canonical_name == "RAV4",
    ).first()
    assert product is not None

    mapping = knowledge_db_session.query(KnowledgeProductBrandMapping).filter(
        KnowledgeProductBrandMapping.vertical_id == vertical_row.id,
        KnowledgeProductBrandMapping.product_id == product.id,
        KnowledgeProductBrandMapping.brand_id == brand.id,
    ).first()
    assert mapping is not None
    assert mapping.is_validated is True

    translation = knowledge_db_session.query(KnowledgeTranslationOverride).filter(
        KnowledgeTranslationOverride.vertical_id == vertical_row.id,
        KnowledgeTranslationOverride.canonical_name == "丰田",
        KnowledgeTranslationOverride.language == "en",
    ).first()
    assert translation is not None
    assert translation.override_text == "Toyota"

    event = knowledge_db_session.query(KnowledgeFeedbackEvent).filter(
        KnowledgeFeedbackEvent.vertical_id == vertical_row.id,
        KnowledgeFeedbackEvent.run_id == run.id,
    ).first()
    assert event is not None
    assert json.loads(json.dumps(event.payload))["run_id"] == run.id


def test_feedback_submit_rejects_pending_run(
    client: TestClient,
    db_session: Session,
):
    vertical = Vertical(name="Phones", description="Smartphones")
    db_session.add(vertical)
    db_session.commit()

    run = Run(vertical_id=vertical.id, model_name="qwen", status=RunStatus.PENDING)
    db_session.add(run)
    db_session.commit()

    payload = {
        "run_id": run.id,
        "vertical_id": vertical.id,
        "canonical_vertical": {"is_new": True, "name": "Phones"},
    }

    response = client.post("/api/v1/feedback/submit", json=payload)

    assert response.status_code == 400
