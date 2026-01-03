import pytest
from datetime import datetime
from sqlalchemy.orm import Session

from models import Vertical
from models.domain import (
    BrandAlias,
    CanonicalBrand,
    CanonicalProduct,
    EntityType,
    ProductAlias,
    RejectedEntity,
    ValidationCandidate,
    ValidationStatus,
)


class TestValidationStatusEnum:

    def test_validation_status_values(self):
        assert ValidationStatus.PENDING.value == "pending"
        assert ValidationStatus.VALIDATED.value == "validated"
        assert ValidationStatus.REJECTED.value == "rejected"

    def test_validation_status_is_string_enum(self):
        assert isinstance(ValidationStatus.PENDING, str)
        assert ValidationStatus.PENDING == "pending"


class TestEntityTypeEnum:

    def test_entity_type_values(self):
        assert EntityType.BRAND.value == "brand"
        assert EntityType.PRODUCT.value == "product"

    def test_entity_type_is_string_enum(self):
        assert isinstance(EntityType.BRAND, str)
        assert EntityType.BRAND == "brand"


class TestCanonicalBrandModel:

    def test_create_canonical_brand(self, db_session: Session):
        vertical = Vertical(name="SUV Cars")
        db_session.add(vertical)
        db_session.flush()

        canonical = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Toyota",
            display_name="Toyota (丰田)",
            is_validated=True,
            validation_source="auto",
            mention_count=5,
        )
        db_session.add(canonical)
        db_session.flush()

        assert canonical.id is not None
        assert canonical.canonical_name == "Toyota"
        assert canonical.display_name == "Toyota (丰田)"
        assert canonical.is_validated is True
        assert canonical.mention_count == 5

    def test_canonical_brand_defaults(self, db_session: Session):
        vertical = Vertical(name="Phones")
        db_session.add(vertical)
        db_session.flush()

        canonical = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Apple",
            display_name="Apple",
        )
        db_session.add(canonical)
        db_session.flush()

        assert canonical.is_validated is False
        assert canonical.validation_source is None
        assert canonical.mention_count == 0

    def test_canonical_brand_with_aliases(self, db_session: Session):
        vertical = Vertical(name="Cars")
        db_session.add(vertical)
        db_session.flush()

        canonical = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Volkswagen",
            display_name="Volkswagen (大众)",
        )
        db_session.add(canonical)
        db_session.flush()

        alias1 = BrandAlias(canonical_brand_id=canonical.id, alias="VW")
        alias2 = BrandAlias(canonical_brand_id=canonical.id, alias="大众")
        db_session.add_all([alias1, alias2])
        db_session.flush()

        db_session.refresh(canonical)
        assert len(canonical.aliases) == 2
        alias_names = [a.alias for a in canonical.aliases]
        assert "VW" in alias_names
        assert "大众" in alias_names


class TestBrandAliasModel:

    def test_create_brand_alias(self, db_session: Session):
        vertical = Vertical(name="Test")
        db_session.add(vertical)
        db_session.flush()

        canonical = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="BMW",
            display_name="BMW",
        )
        db_session.add(canonical)
        db_session.flush()

        alias = BrandAlias(
            canonical_brand_id=canonical.id,
            alias="宝马",
        )
        db_session.add(alias)
        db_session.flush()

        assert alias.id is not None
        assert alias.alias == "宝马"
        assert alias.canonical_brand_id == canonical.id

    def test_alias_relationship_to_canonical(self, db_session: Session):
        vertical = Vertical(name="Test2")
        db_session.add(vertical)
        db_session.flush()

        canonical = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Mercedes",
            display_name="Mercedes-Benz",
        )
        db_session.add(canonical)
        db_session.flush()

        alias = BrandAlias(
            canonical_brand_id=canonical.id,
            alias="奔驰",
        )
        db_session.add(alias)
        db_session.flush()

        db_session.refresh(alias)
        assert alias.canonical_brand.canonical_name == "Mercedes"


class TestCanonicalProductModel:

    def test_create_canonical_product(self, db_session: Session):
        vertical = Vertical(name="SUV")
        db_session.add(vertical)
        db_session.flush()

        canonical_brand = CanonicalBrand(
            vertical_id=vertical.id,
            canonical_name="Toyota",
            display_name="Toyota",
        )
        db_session.add(canonical_brand)
        db_session.flush()

        product = CanonicalProduct(
            vertical_id=vertical.id,
            canonical_brand_id=canonical_brand.id,
            canonical_name="RAV4",
            display_name="RAV4",
            is_validated=True,
            mention_count=3,
        )
        db_session.add(product)
        db_session.flush()

        assert product.id is not None
        assert product.canonical_name == "RAV4"
        assert product.canonical_brand_id == canonical_brand.id

    def test_canonical_product_without_brand(self, db_session: Session):
        vertical = Vertical(name="Generic")
        db_session.add(vertical)
        db_session.flush()

        product = CanonicalProduct(
            vertical_id=vertical.id,
            canonical_name="Unknown Product",
            display_name="Unknown Product",
        )
        db_session.add(product)
        db_session.flush()

        assert product.id is not None
        assert product.canonical_brand_id is None


class TestProductAliasModel:

    def test_create_product_alias(self, db_session: Session):
        vertical = Vertical(name="Test")
        db_session.add(vertical)
        db_session.flush()

        product = CanonicalProduct(
            vertical_id=vertical.id,
            canonical_name="Model Y",
            display_name="Model Y",
        )
        db_session.add(product)
        db_session.flush()

        alias = ProductAlias(
            canonical_product_id=product.id,
            alias="特斯拉Model Y",
        )
        db_session.add(alias)
        db_session.flush()

        assert alias.id is not None
        assert alias.alias == "特斯拉Model Y"


class TestValidationCandidateModel:

    def test_create_validation_candidate(self, db_session: Session):
        vertical = Vertical(name="Cars")
        db_session.add(vertical)
        db_session.flush()

        candidate = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.BRAND,
            name="Haval",
            mention_count=2,
            status=ValidationStatus.PENDING,
        )
        db_session.add(candidate)
        db_session.flush()

        assert candidate.id is not None
        assert candidate.entity_type == EntityType.BRAND
        assert candidate.status == ValidationStatus.PENDING
        assert candidate.mention_count == 2

    def test_validation_candidate_defaults(self, db_session: Session):
        vertical = Vertical(name="Cars2")
        db_session.add(vertical)
        db_session.flush()

        candidate = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.PRODUCT,
            name="Song Plus",
        )
        db_session.add(candidate)
        db_session.flush()

        assert candidate.status == ValidationStatus.PENDING
        assert candidate.mention_count == 0
        assert candidate.reviewed_at is None
        assert candidate.reviewed_by is None

    def test_update_validation_status(self, db_session: Session):
        vertical = Vertical(name="Cars3")
        db_session.add(vertical)
        db_session.flush()

        candidate = ValidationCandidate(
            vertical_id=vertical.id,
            entity_type=EntityType.BRAND,
            name="Geely",
            status=ValidationStatus.PENDING,
        )
        db_session.add(candidate)
        db_session.flush()

        candidate.status = ValidationStatus.VALIDATED
        candidate.reviewed_at = datetime.utcnow()
        candidate.reviewed_by = "user"
        db_session.flush()

        db_session.refresh(candidate)
        assert candidate.status == ValidationStatus.VALIDATED
        assert candidate.reviewed_by == "user"


class TestRejectedEntityModel:

    def test_create_rejected_entity(self, db_session: Session):
        vertical = Vertical(name="Cars4")
        db_session.add(vertical)
        db_session.flush()

        rejected = RejectedEntity(
            vertical_id=vertical.id,
            entity_type=EntityType.BRAND,
            name="Not A Brand",
            rejection_reason="Generic term, not a brand name",
            example_context="The not a brand product is great",
        )
        db_session.add(rejected)
        db_session.flush()

        assert rejected.id is not None
        assert rejected.entity_type == EntityType.BRAND
        assert rejected.rejection_reason == "Generic term, not a brand name"

    def test_rejected_entity_without_context(self, db_session: Session):
        vertical = Vertical(name="Cars5")
        db_session.add(vertical)
        db_session.flush()

        rejected = RejectedEntity(
            vertical_id=vertical.id,
            entity_type=EntityType.PRODUCT,
            name="SUV",
            rejection_reason="Generic product category",
        )
        db_session.add(rejected)
        db_session.flush()

        assert rejected.id is not None
        assert rejected.example_context is None
