import pytest
from sqlalchemy.orm import Session

from models import Brand, Product, Vertical
from services.product_discovery import (
    discover_products_in_text,
    get_or_create_product,
    link_product_to_brand,
    BRAND_PRODUCT_MAP,
)


class TestProductBrandLinking:

    def test_known_product_links_to_brand(self):
        assert BRAND_PRODUCT_MAP.get("rav4") == "toyota"
        assert BRAND_PRODUCT_MAP.get("crv") == "honda"
        assert BRAND_PRODUCT_MAP.get("model y") == "tesla"
        assert BRAND_PRODUCT_MAP.get("宋plus") == "比亚迪"
        assert BRAND_PRODUCT_MAP.get("x5") == "bmw"

    def test_product_with_brand_context(self):
        products = discover_products_in_text(
            "Honda CRV is a great choice",
            vertical="SUV cars"
        )
        assert len(products) >= 1
        crv = next((p for p in products if "crv" in p["name"].lower()), None)
        assert crv is not None
        assert crv["parent_brand"].lower() == "honda"

    def test_multiple_products_discovered(self):
        products = discover_products_in_text(
            "1. Toyota RAV4 is excellent\n2. Honda CRV is also good",
            vertical="SUV cars"
        )
        assert len(products) >= 2


class TestProductStorage:

    def test_get_or_create_product_new(self, db_session: Session):
        vertical = Vertical(name="Test Vertical")
        db_session.add(vertical)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="Toyota",
            original_name="Toyota",
            aliases={"zh": ["丰田"], "en": []},
            is_user_input=True,
        )
        db_session.add(brand)
        db_session.flush()

        product = get_or_create_product(
            db=db_session,
            vertical_id=vertical.id,
            product_name="RAV4",
            brand_id=brand.id,
        )

        assert product.id is not None
        assert product.display_name == "RAV4"
        assert product.brand_id == brand.id
        assert product.vertical_id == vertical.id

    def test_get_or_create_product_existing(self, db_session: Session):
        vertical = Vertical(name="Test Vertical 2")
        db_session.add(vertical)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="Honda",
            original_name="Honda",
            aliases={"zh": ["本田"], "en": []},
            is_user_input=True,
        )
        db_session.add(brand)
        db_session.flush()

        product1 = get_or_create_product(
            db=db_session,
            vertical_id=vertical.id,
            product_name="CRV",
            brand_id=brand.id,
        )

        product2 = get_or_create_product(
            db=db_session,
            vertical_id=vertical.id,
            product_name="CRV",
            brand_id=brand.id,
        )

        assert product1.id == product2.id

    def test_link_product_to_brand(self, db_session: Session):
        vertical = Vertical(name="Test Vertical 3")
        db_session.add(vertical)
        db_session.flush()

        brand = Brand(
            vertical_id=vertical.id,
            display_name="BYD",
            original_name="比亚迪",
            aliases={"zh": [], "en": []},
            is_user_input=True,
        )
        db_session.add(brand)
        db_session.flush()

        product = Product(
            vertical_id=vertical.id,
            display_name="宋PLUS",
            original_name="宋PLUS",
            brand_id=None,
        )
        db_session.add(product)
        db_session.flush()

        link_product_to_brand(db_session, product.id, brand.id)
        db_session.refresh(product)

        assert product.brand_id == brand.id


class TestProductDiscovery:

    def test_discover_product_with_known_brand(self):
        products = discover_products_in_text(
            "比亚迪宋PLUS DM-i是非常好的选择",
            vertical="SUV cars"
        )
        assert len(products) >= 1
        song = next((p for p in products if "宋" in p["name"]), None)
        assert song is not None
        assert song["parent_brand"] in ["比亚迪", "BYD", "byd"]

    def test_discover_ignores_generic_terms(self):
        products = discover_products_in_text(
            "SUV is a great vehicle type",
            vertical="SUV cars"
        )
        suv_product = next((p for p in products if p["name"].lower() == "suv"), None)
        assert suv_product is None
