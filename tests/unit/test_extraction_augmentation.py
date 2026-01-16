from sqlalchemy.orm import Session

from models import Brand, Vertical
from models.domain import EntityType
from models.knowledge_domain import KnowledgeRejectedEntity, KnowledgeVertical
from services.ai_corrections.persistence import create_audit_run, add_applied_items
from services.brand_recognition.extraction_augmentation import (
    get_rejected_brands_for_prompt,
    get_augmentation_context,
    get_validated_entity_names,
)
from services.knowledge_session import knowledge_session


def test_validated_brand_names_include_user_aliases(db_session: Session):
    vertical = Vertical(name="Validated Brands")
    db_session.add(vertical)
    db_session.flush()

    user_brand = Brand(
        vertical_id=vertical.id,
        display_name="VW",
        original_name="VW",
        translated_name="VW",
        aliases={"zh": ["大众"], "en": ["Volkswagen"]},
        is_user_input=True,
    )
    db_session.add(user_brand)
    db_session.flush()

    brand_names, _ = get_validated_entity_names(db_session, vertical.id)

    assert "VW" in brand_names
    assert "大众" in brand_names
    assert "Volkswagen" in brand_names


def test_rejected_examples_empty_when_no_knowledge_vertical_match(
    db_session: Session,
    knowledge_db_session: Session,
):
    vertical = Vertical(name="New Vertical")
    db_session.add(vertical)
    db_session.flush()

    other = KnowledgeVertical(name="Other")
    knowledge_db_session.add(other)
    knowledge_db_session.flush()

    knowledge_db_session.add(
        KnowledgeRejectedEntity(
            vertical_id=other.id,
            entity_type=EntityType.BRAND,
            name="四驱",
            reason="too_generic",
        )
    )
    knowledge_db_session.flush()

    rejected = get_rejected_brands_for_prompt(db_session, vertical.id)
    assert rejected == []


def test_augmentation_context_includes_correction_examples(db_session: Session):
    from models import Vertical

    vertical = Vertical(name="Cars")
    db_session.add(vertical)
    db_session.flush()

    with knowledge_session(write=True) as knowledge_db:
        knowledge_vertical = KnowledgeVertical(name=vertical.name)
        knowledge_db.add(knowledge_vertical)
        knowledge_db.flush()

        audit = create_audit_run(
            knowledge_db,
            run_id=1,
            tracking_vertical_id=int(vertical.id),
            vertical_id=int(knowledge_vertical.id),
            requested_provider="deepseek",
            requested_model="deepseek-reasoner",
            resolved_provider="deepseek",
            resolved_model="deepseek-reasoner",
            resolved_route="vendor",
            thresholds={},
            min_confidence_levels={},
            dry_run=False,
            scope="run",
        )
        add_applied_items(
            knowledge_db,
            audit.id,
            [
                {
                    "run_id": 1,
                    "llm_answer_id": 11,
                    "category": "Mapping",
                    "action": "add_mapping",
                    "confidence_level": "VERY_HIGH",
                    "confidence_score": 0.99,
                    "reason": "explicit",
                    "evidence_quote_zh": "推荐 BYD 的 宋PLUS",
                    "feedback_payload": {
                        "run_id": 1,
                        "vertical_id": int(vertical.id),
                        "canonical_vertical": {"id": int(knowledge_vertical.id), "is_new": False},
                        "brand_feedback": [],
                        "product_feedback": [],
                        "mapping_feedback": [{"action": "add", "product_name": "宋PLUS", "brand_name": "BYD"}],
                        "translation_overrides": [],
                    },
                }
            ],
        )

    context = get_augmentation_context(db_session, vertical.id)
    examples = context.get("correction_examples") or []
    assert len(examples) == 1
    assert "BYD" in examples[0]["trigger"]
    assert "parent_brand" in examples[0]["rules"][0]
