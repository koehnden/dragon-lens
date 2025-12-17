from models import Brand, Product, Vertical
from models.domain import EntityType
from services.brand_discovery import build_entity_targets, discover_all_brands


def _create_brand(db_session, vertical_id, name):
    brand = Brand(
        vertical_id=vertical_id,
        display_name=name,
        original_name=name,
        translated_name=name,
        aliases={"zh": [], "en": []},
        entity_type=EntityType.BRAND,
    )
    db_session.add(brand)
    db_session.flush()
    return brand


def test_discover_all_brands_registers_products(db_session, monkeypatch):
    vertical = Vertical(name="Cars")
    db_session.add(vertical)
    db_session.flush()

    toyota = _create_brand(db_session, vertical.id, "Toyota")
    honda = _create_brand(db_session, vertical.id, "Honda")

    def fake_extract_entities(text, primary_brand, aliases):
        return {
            "Toyota RAV4": ["Toyota RAV4"],
            "Honda CRV": ["Honda CRV"],
        }

    monkeypatch.setattr(
        "services.brand_discovery.extract_entities", fake_extract_entities
    )

    entities = discover_all_brands("text", vertical.id, [toyota, honda], db_session)

    product_names = sorted(p.original_name for p in entities.products)
    assert product_names == ["Honda CRV", "Toyota RAV4"]
    assert {p.brand_id for p in entities.products} == {toyota.id, honda.id}
    assert len(entities.brands) == 2


def test_build_entity_targets_includes_products(db_session):
    vertical = Vertical(name="Cars")
    db_session.add(vertical)
    db_session.flush()

    toyota = _create_brand(db_session, vertical.id, "Toyota")
    product = Product(
        brand_id=toyota.id,
        original_name="Toyota RAV4",
        translated_name="Toyota RAV4",
    )
    db_session.add(product)
    db_session.flush()

    targets = build_entity_targets([toyota], [product])

    assert [t.name for t in targets] == ["Toyota", "Toyota RAV4"]
    assert [t.brand_id for t in targets] == [toyota.id, toyota.id]
    assert [t.entity_type for t in targets] == [EntityType.BRAND, EntityType.PRODUCT]
