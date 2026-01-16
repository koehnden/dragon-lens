from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeProduct,
    KnowledgeProductBrandMapping,
    KnowledgeVertical,
)


def test_build_cache_prefers_feedback_mapping(knowledge_db_session):
    from services.knowledge_lookup import _build_cache_for_vertical

    vertical = KnowledgeVertical(name="Cars")
    knowledge_db_session.add(vertical)
    knowledge_db_session.flush()

    product = KnowledgeProduct(
        vertical_id=vertical.id,
        brand_id=None,
        canonical_name="rav4",
        display_name="RAV4",
        is_validated=True,
        validation_source="test",
    )
    knowledge_db_session.add(product)
    knowledge_db_session.flush()

    toyota = KnowledgeBrand(
        vertical_id=vertical.id,
        canonical_name="toyota",
        display_name="Toyota",
        is_validated=True,
        validation_source="test",
    )
    honda = KnowledgeBrand(
        vertical_id=vertical.id,
        canonical_name="honda",
        display_name="Honda",
        is_validated=True,
        validation_source="test",
    )
    knowledge_db_session.add_all([toyota, honda])
    knowledge_db_session.flush()

    knowledge_db_session.add(
        KnowledgeProductBrandMapping(
            vertical_id=vertical.id,
            product_id=product.id,
            brand_id=honda.id,
            is_validated=True,
            source="auto_support",
            support_count=20,
            confidence=0.95,
        )
    )
    knowledge_db_session.add(
        KnowledgeProductBrandMapping(
            vertical_id=vertical.id,
            product_id=product.id,
            brand_id=toyota.id,
            is_validated=True,
            source="feedback",
            support_count=0,
            confidence=0.0,
        )
    )
    knowledge_db_session.commit()

    cache = _build_cache_for_vertical(knowledge_db_session, vertical.id)
    assert cache["rav4"] == "Toyota"
    assert cache["rav4".lower()] == "Toyota"
    assert cache["rav4".upper().lower()] == "Toyota"


def test_build_cache_ignores_unvalidated_mappings(knowledge_db_session):
    from services.knowledge_lookup import _build_cache_for_vertical

    vertical = KnowledgeVertical(name="Cars")
    knowledge_db_session.add(vertical)
    knowledge_db_session.flush()

    product = KnowledgeProduct(
        vertical_id=vertical.id,
        brand_id=None,
        canonical_name="rav4",
        display_name="RAV4",
        is_validated=True,
        validation_source="test",
    )
    brand = KnowledgeBrand(
        vertical_id=vertical.id,
        canonical_name="toyota",
        display_name="Toyota",
        is_validated=True,
        validation_source="test",
    )
    knowledge_db_session.add_all([product, brand])
    knowledge_db_session.flush()
    knowledge_db_session.add(
        KnowledgeProductBrandMapping(
            vertical_id=vertical.id,
            product_id=product.id,
            brand_id=brand.id,
            is_validated=False,
            source="auto_list_evidence",
            support_count=100,
            confidence=1.0,
        )
    )
    knowledge_db_session.commit()

    cache = _build_cache_for_vertical(knowledge_db_session, vertical.id)
    assert cache == {}
