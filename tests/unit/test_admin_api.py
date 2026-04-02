from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from config import settings
from models import Brand, LLMAnswer, Prompt, PromptLanguage, Run, RunStatus, Vertical
from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductBrandMapping,
    KnowledgeRejectedEntity,
    KnowledgeTranslationOverride,
    KnowledgeVertical,
    KnowledgeVerticalAlias,
)
from services.demo_publish import build_demo_publish_request


def test_public_demo_blocks_non_admin_mutations(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "app_mode", "public_demo")

    response = client.post("/api/v1/verticals", json={"name": "Cars"})

    assert response.status_code == 403
    assert response.json() == {"detail": "Public demo mode is read-only"}


def test_public_demo_allows_admin_knowledge_sync_with_token(
    client: TestClient,
    knowledge_db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "app_mode", "public_demo")
    monkeypatch.setattr(settings, "admin_api_token", "secret-token")
    payload = {
        "submission_id": "sync-1",
        "source_app_version": "test",
        "vertical_name": "Cars",
        "vertical_description": "Vehicles",
        "vertical_aliases": ["SUV Cars"],
        "brands": [
            {
                "canonical_name": "toyota",
                "display_name": "Toyota",
                "is_validated": True,
                "validation_source": "admin",
                "mention_count": 10,
                "aliases": [{"alias": "丰田", "language": "zh"}],
            }
        ],
        "products": [
            {
                "canonical_name": "rav4",
                "display_name": "RAV4",
                "brand_canonical_name": "toyota",
                "is_validated": True,
                "validation_source": "admin",
                "mention_count": 5,
            }
        ],
        "mappings": [
            {
                "product_canonical_name": "rav4",
                "brand_canonical_name": "toyota",
                "is_validated": True,
                "source": "admin",
            }
        ],
        "rejected_entities": [
            {"entity_type": "brand", "name": "BMW X5", "reason": "product not brand"}
        ],
        "translation_overrides": [
            {
                "entity_type": "brand",
                "canonical_name": "toyota",
                "language": "en",
                "override_text": "Toyota",
                "reason": "display standardization",
            }
        ],
    }

    response = client.post(
        "/api/v1/admin/knowledge-sync",
        json=payload,
        headers={"Authorization": "Bearer secret-token"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["created_counts"]["brands"] == 1
    assert body["created_counts"]["products"] == 1
    assert (
        knowledge_db_session.query(KnowledgeVertical)
        .filter(KnowledgeVertical.name == "Cars")
        .count()
        == 1
    )
    assert (
        knowledge_db_session.query(KnowledgeVerticalAlias)
        .filter(KnowledgeVerticalAlias.alias == "SUV Cars")
        .count()
        == 1
    )
    assert (
        knowledge_db_session.query(KnowledgeBrand)
        .filter(KnowledgeBrand.canonical_name == "toyota")
        .count()
        == 1
    )
    assert (
        knowledge_db_session.query(KnowledgeBrandAlias)
        .filter(KnowledgeBrandAlias.alias == "丰田")
        .count()
        == 1
    )
    assert (
        knowledge_db_session.query(KnowledgeProduct)
        .filter(KnowledgeProduct.canonical_name == "rav4")
        .count()
        == 1
    )
    assert knowledge_db_session.query(KnowledgeProductBrandMapping).count() == 1
    assert knowledge_db_session.query(KnowledgeRejectedEntity).count() == 1
    assert knowledge_db_session.query(KnowledgeTranslationOverride).count() == 1


def test_admin_knowledge_sync_requires_token(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "app_mode", "local_admin")
    monkeypatch.setattr(settings, "admin_api_token", "secret-token")

    response = client.post(
        "/api/v1/admin/knowledge-sync",
        json={"submission_id": "sync-1", "vertical_name": "Cars"},
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Unauthorized"}


def test_demo_publish_replaces_existing_snapshot(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "demo_publish_token", "publish-secret")
    vertical = _seed_demo_vertical(db_session)
    payload = build_demo_publish_request(db_session, vertical.id, "publish-1")
    _add_legacy_brand(db_session, vertical.id)
    db_session.commit()

    response = client.post(
        "/api/v1/admin/demo-publish",
        json=payload.model_dump(mode="json"),
        headers={"Authorization": "Bearer publish-secret"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["vertical_id"] > 0
    names = [
        brand.display_name
        for brand in db_session.query(Brand)
        .join(Vertical, Brand.vertical_id == Vertical.id)
        .filter(Vertical.name == "Cars")
        .order_by(Brand.display_name.asc())
        .all()
    ]
    assert names == ["Toyota"]
    assert (
        db_session.query(Run)
        .join(Vertical, Run.vertical_id == Vertical.id)
        .filter(Vertical.name == "Cars")
        .count()
        == 1
    )


def _seed_demo_vertical(db_session: Session) -> Vertical:
    vertical = Vertical(name="Cars", description="Vehicles")
    db_session.add(vertical)
    db_session.flush()
    brand = Brand(
        vertical_id=vertical.id,
        display_name="Toyota",
        original_name="Toyota",
        aliases={"en": ["Toyota"]},
    )
    db_session.add(brand)
    db_session.flush()
    run = Run(
        vertical_id=vertical.id,
        provider="qwen",
        model_name="qwen-plus",
        status=RunStatus.COMPLETED,
        run_time=datetime(2026, 4, 2, tzinfo=timezone.utc),
        completed_at=datetime(2026, 4, 2, tzinfo=timezone.utc),
    )
    db_session.add(run)
    db_session.flush()
    prompt = Prompt(
        vertical_id=vertical.id,
        run_id=run.id,
        text_en="Best SUVs in China?",
        text_zh="中国最好的SUV是什么？",
        language_original=PromptLanguage.EN,
    )
    db_session.add(prompt)
    db_session.flush()
    db_session.add(
        LLMAnswer(
            run_id=run.id,
            prompt_id=prompt.id,
            provider="qwen",
            model_name="qwen-plus",
            raw_answer_zh="丰田是一个强势品牌。",
            raw_answer_en="Toyota is a strong brand.",
        )
    )
    db_session.flush()
    return vertical


def _add_legacy_brand(db_session: Session, vertical_id: int) -> None:
    db_session.add(
        Brand(
            vertical_id=vertical_id,
            display_name="Legacy Brand",
            original_name="Legacy Brand",
            aliases={},
        )
    )
