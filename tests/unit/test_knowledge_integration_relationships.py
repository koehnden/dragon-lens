from services.brand_recognition.knowledge_integration import (
    KnowledgeExtractionContext,
    apply_knowledge_to_extraction,
)


def _context(
    brand_lookup: dict[str, str] | None = None,
    product_lookup: dict[str, str] | None = None,
    rejected_brands: set[str] | None = None,
) -> KnowledgeExtractionContext:
    return KnowledgeExtractionContext(
        canonical_vertical_id=1,
        brand_lookup=brand_lookup or {},
        product_lookup=product_lookup or {},
        rejected_brands=rejected_brands or set(),
        rejected_products=set(),
        validated_product_brand={},
    )


def test_relationship_skips_rejected_brand_surface():
    context = _context(rejected_brands={"BadBrand"})
    brands, products, rel = apply_knowledge_to_extraction(
        brands=["GoodBrand"],
        products=["P1"],
        relationships={"P1": "BadBrand"},
        context=context,
    )
    assert "BadBrand" not in brands
    assert rel == {}


def test_relationship_skips_rejected_brand_after_canonicalization():
    context = _context(brand_lookup={"byd auto": "BYD"}, rejected_brands={"BYD"})
    brands, products, rel = apply_knowledge_to_extraction(
        brands=["GoodBrand"],
        products=["P1"],
        relationships={"P1": "BYD Auto"},
        context=context,
    )
    assert "BYD" not in brands
    assert rel == {}
