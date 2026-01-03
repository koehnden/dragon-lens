from services.brand_recognition.product_brand_mapping import (
    build_mapping_prompt,
    select_mapping_examples,
)


def test_load_mapping_examples_from_db(db_session):
    from models import Brand, Product, ProductBrandMapping, Vertical
    from services.brand_recognition.product_brand_mapping import load_mapping_examples

    vertical = Vertical(name="Cars")
    db_session.add(vertical)
    db_session.flush()
    brand = Brand(
        vertical_id=vertical.id,
        display_name="Orion",
        original_name="Orion",
        translated_name=None,
        aliases={"zh": [], "en": []},
        is_user_input=True,
    )
    db_session.add(brand)
    db_session.flush()
    product = Product(
        vertical_id=vertical.id,
        brand_id=brand.id,
        display_name="Nova X2",
        original_name="Nova X2",
        translated_name=None,
        is_user_input=False,
    )
    db_session.add(product)
    db_session.flush()
    mapping = ProductBrandMapping(
        vertical_id=vertical.id,
        product_id=product.id,
        brand_id=brand.id,
        confidence=0.9,
        is_validated=True,
        source="test",
    )
    db_session.add(mapping)
    db_session.commit()

    examples = load_mapping_examples(db_session, vertical.id)

    assert examples[0]["product"] == "Nova X2"
    assert examples[0]["brand"] == "Orion"


def test_mapping_prompt_includes_known_mappings():
    known = [{"product": "Nova X2", "brand": "Orion", "confidence": 0.9, "is_validated": True}]
    prompt = build_mapping_prompt("Nova X2", ["Orion"], ["Nova X2 is good"], known)
    assert "Nova X2" in prompt and "Orion" in prompt


def test_select_mapping_examples_limits_to_20():
    mappings = [{"product": f"P{i}", "brand": f"B{i}", "confidence": 0.9, "is_validated": True} for i in range(25)]
    examples = select_mapping_examples(mappings)
    assert len(examples) == 20


def test_select_mapping_examples_filters_low_confidence():
    mappings = [{"product": "P", "brand": "B", "confidence": 0.2, "is_validated": False}]
    examples = select_mapping_examples(mappings)
    assert examples == []
