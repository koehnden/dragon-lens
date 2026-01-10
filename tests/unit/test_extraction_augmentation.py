from sqlalchemy.orm import Session

from models import Brand, Vertical
from models.domain import EntityType
from models.knowledge_domain import KnowledgeRejectedEntity, KnowledgeVertical
from services.brand_recognition.extraction_augmentation import (
    get_rejected_brands_for_prompt,
    get_validated_entity_names,
)


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
