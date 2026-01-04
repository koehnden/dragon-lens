from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from models.knowledge_domain import KnowledgeVertical


def test_list_knowledge_verticals_empty(client: TestClient):
    response = client.get("/api/v1/knowledge/verticals")
    assert response.status_code == 200
    assert response.json() == []


def test_list_knowledge_verticals(client: TestClient, knowledge_db_session: Session):
    knowledge_db_session.add_all([
        KnowledgeVertical(name="Cars", description="Vehicles"),
        KnowledgeVertical(name="Phones", description="Devices"),
    ])
    knowledge_db_session.commit()

    response = client.get("/api/v1/knowledge/verticals")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    names = {item["name"] for item in data}
    assert "Cars" in names
    assert "Phones" in names
