from services.brand_recognition.knowledge_integration import (
    KnowledgeExtractionContext,
    apply_knowledge_to_extraction,
    build_knowledge_extraction_context,
)


def test_apply_knowledge_filters_rejected_and_canonicalizes_and_overrides_mappings():
    context = KnowledgeExtractionContext(
        canonical_vertical_id=1,
        brand_lookup={
            "比亚迪": "BYD",
            "byd": "BYD",
            "byd auto": "BYD",
        },
        product_lookup={
            "宋plus dm-i": "Song Plus",
            "宋plus": "Song Plus",
        },
        rejected_brands={"特斯拉"},
        rejected_products=set(),
        validated_product_brand={"Song Plus": "BYD"},
    )

    brands = ["比亚迪", "特斯拉"]
    products = ["宋PLUS DM-i"]
    relationships = {"宋PLUS DM-i": "比亚迪"}

    out_brands, out_products, out_relationships = apply_knowledge_to_extraction(
        brands, products, relationships, context
    )

    assert "BYD" in out_brands
    assert out_brands["BYD"] == ["比亚迪"]
    assert "特斯拉" not in out_brands

    assert "Song Plus" in out_products
    assert out_products["Song Plus"] == ["宋PLUS DM-i"]

    assert out_relationships == {"Song Plus": "BYD"}


def test_apply_knowledge_adds_missing_brand_from_validated_mapping():
    context = KnowledgeExtractionContext(
        canonical_vertical_id=1,
        brand_lookup={"比亚迪": "BYD"},
        product_lookup={"宋plus": "Song Plus"},
        rejected_brands=set(),
        rejected_products=set(),
        validated_product_brand={"Song Plus": "BYD"},
    )

    brands = []
    products = ["宋PLUS"]
    relationships = {}

    out_brands, out_products, out_relationships = apply_knowledge_to_extraction(
        brands, products, relationships, context
    )

    assert "BYD" in out_brands
    assert out_relationships == {"Song Plus": "BYD"}


def test_apply_knowledge_brand_suffix_stripping_falls_back_to_canonical():
    context = KnowledgeExtractionContext(
        canonical_vertical_id=1,
        brand_lookup={"byd": "BYD"},
        product_lookup={},
        rejected_brands=set(),
        rejected_products=set(),
        validated_product_brand={},
    )
    out_brands, _, _ = apply_knowledge_to_extraction(["BYD Auto"], [], {}, context)
    assert "BYD" in out_brands
    assert out_brands["BYD"] == ["BYD Auto"]


def test_context_resolves_alias_vertical_to_canonical(knowledge_db_session):
    from models.knowledge_domain import (
        KnowledgeBrand,
        KnowledgeBrandAlias,
        KnowledgeVertical,
        KnowledgeVerticalAlias,
    )

    canonical = KnowledgeVertical(name="Car", description=None)
    knowledge_db_session.add(canonical)
    knowledge_db_session.commit()
    knowledge_db_session.refresh(canonical)

    knowledge_db_session.add(
        KnowledgeVerticalAlias(vertical_id=canonical.id, alias="SUV", alias_key="suv", source="test")
    )
    knowledge_db_session.add(
        KnowledgeBrand(vertical_id=canonical.id, canonical_name="BYD", display_name="BYD", is_validated=True)
    )
    knowledge_db_session.commit()
    brand = knowledge_db_session.query(KnowledgeBrand).filter(KnowledgeBrand.vertical_id == canonical.id).first()
    knowledge_db_session.add(KnowledgeBrandAlias(brand_id=brand.id, alias="比亚迪", language="zh"))
    knowledge_db_session.commit()

    ctx = build_knowledge_extraction_context(knowledge_db_session, "SUV")
    assert ctx is not None
    assert ctx.canonical_vertical_id == canonical.id
    assert ctx.brand_lookup.get("比亚迪") == "BYD"
