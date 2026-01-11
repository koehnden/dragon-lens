"""Integration tests for vertical alias uniqueness."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models import Vertical
from models.knowledge_domain import KnowledgeVerticalAlias
from services.knowledge_verticals import normalize_entity_key


def test_vertical_alias_rejects_duplicate_alias_key(
    client: TestClient,
    db_session: Session,
    knowledge_db_session: Session,
) -> None:
    vertical = Vertical(name="SUV Cars", description="SUV")
    db_session.add(vertical)
    db_session.commit()
    db_session.refresh(vertical)

    first = client.post(
        "/api/v1/feedback/vertical-alias",
        json={
            "vertical_id": vertical.id,
            "canonical_vertical": {"is_new": True, "name": "Cars A"},
        },
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/feedback/vertical-alias",
        json={
            "vertical_id": vertical.id,
            "canonical_vertical": {"is_new": True, "name": "Cars B"},
        },
    )
    assert second.status_code == 409

    alias_key = normalize_entity_key(vertical.name)
    aliases = knowledge_db_session.query(KnowledgeVerticalAlias).filter(
        KnowledgeVerticalAlias.alias_key == alias_key
    ).all()
    assert len(aliases) == 1
