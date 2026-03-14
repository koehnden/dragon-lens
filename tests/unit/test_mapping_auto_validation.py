from models.knowledge_domain import KnowledgeVertical


def _create_vertical(db, name: str) -> KnowledgeVertical:
    vertical = KnowledgeVertical(name=name)
    db.add(vertical)
    db.flush()
    return vertical


def test_auto_validation_applies_and_revokes_on_ambiguity(knowledge_db_session):
    from services.brand_recognition.product_brand_mapping import (
        _apply_auto_validation_policy,
        _get_or_create_knowledge_brand,
        _get_or_create_knowledge_product,
        _recompute_mapping_confidence,
        _upsert_knowledge_mapping,
    )
    from models.knowledge_domain import KnowledgeProductBrandMapping

    vertical = _create_vertical(knowledge_db_session, "Cars")
    product = _get_or_create_knowledge_product(knowledge_db_session, vertical.id, "RAV4")
    toyota = _get_or_create_knowledge_brand(knowledge_db_session, vertical.id, "Toyota")
    honda = _get_or_create_knowledge_brand(knowledge_db_session, vertical.id, "Honda")

    _upsert_knowledge_mapping(knowledge_db_session, vertical.id, product.id, toyota.id, "auto_list_evidence", 20)
    _upsert_knowledge_mapping(knowledge_db_session, vertical.id, product.id, honda.id, "auto_list_evidence", 1)
    _recompute_mapping_confidence(knowledge_db_session, vertical.id, product.id)
    _apply_auto_validation_policy(knowledge_db_session, vertical.id, product.id)

    mapping = knowledge_db_session.query(KnowledgeProductBrandMapping).filter(
        KnowledgeProductBrandMapping.vertical_id == vertical.id,
        KnowledgeProductBrandMapping.product_id == product.id,
        KnowledgeProductBrandMapping.brand_id == toyota.id,
    ).first()
    assert mapping is not None
    assert mapping.is_validated is True
    assert mapping.source == "auto_support"

    _upsert_knowledge_mapping(knowledge_db_session, vertical.id, product.id, honda.id, "auto_list_evidence", 1)
    _recompute_mapping_confidence(knowledge_db_session, vertical.id, product.id)
    _apply_auto_validation_policy(knowledge_db_session, vertical.id, product.id)

    knowledge_db_session.flush()
    knowledge_db_session.refresh(mapping)
    assert mapping.is_validated is False


def test_feedback_validated_wins_over_auto_support(knowledge_db_session):
    from services.brand_recognition.product_brand_mapping import (
        _apply_auto_validation_policy,
        _get_or_create_knowledge_brand,
        _get_or_create_knowledge_product,
        _upsert_knowledge_mapping,
    )
    from models.knowledge_domain import KnowledgeProductBrandMapping

    vertical = _create_vertical(knowledge_db_session, "Cars")
    product = _get_or_create_knowledge_product(knowledge_db_session, vertical.id, "RAV4")
    toyota = _get_or_create_knowledge_brand(knowledge_db_session, vertical.id, "Toyota")
    honda = _get_or_create_knowledge_brand(knowledge_db_session, vertical.id, "Honda")

    auto = _upsert_knowledge_mapping(knowledge_db_session, vertical.id, product.id, honda.id, "auto_support", 0)
    auto.is_validated = True
    auto.source = "auto_support"

    feedback = _upsert_knowledge_mapping(knowledge_db_session, vertical.id, product.id, toyota.id, "feedback", 0)
    feedback.is_validated = True
    feedback.source = "feedback"

    _apply_auto_validation_policy(knowledge_db_session, vertical.id, product.id)

    knowledge_db_session.flush()
    knowledge_db_session.refresh(auto)
    knowledge_db_session.refresh(feedback)

    assert feedback.is_validated is True
    assert feedback.source == "feedback"
    assert auto.is_validated is False
