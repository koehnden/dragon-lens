from sqlalchemy.orm import Session

from models import RejectedEntity, Vertical
from models.domain import EntityType
from services.brand_recognition.consolidation_service import (
    AnswerEntities,
    _store_rejected_entities,
    apply_list_position_filter_per_answer,
)


def test_list_filter_rejections_are_split():
    answer = AnswerEntities(
        answer_id=1,
        answer_text="1. BrandA ProductX and BrandB ProductY\n2. BrandA ProductX",
        raw_brands=["BrandA", "BrandB"],
        raw_products=["ProductX", "ProductY"],
    )
    kept_brands, kept_products, rejected_brands, rejected_products = apply_list_position_filter_per_answer(
        answer,
        brand_mapping={"BrandA": "BrandA", "BrandB": "BrandB"},
        valid_products={"ProductX", "ProductY"},
    )

    assert kept_brands == {"BrandA"}
    assert kept_products == {"ProductX"}
    assert set(rejected_brands) == {"BrandB"}
    assert set(rejected_products) == {"ProductY"}


def test_store_rejected_entities_saves_list_filter_types(db_session: Session):
    vertical = Vertical(name="Test Vertical")
    db_session.add(vertical)
    db_session.flush()

    _store_rejected_entities(
        db_session,
        vertical.id,
        rejected_at_normalization=[],
        rejected_at_validation=[],
        rejected_at_list_filter_brands=["BrandB"],
        rejected_at_list_filter_products=["ProductY"],
        rejected_at_light_filter=[],
    )
    db_session.commit()

    brand_rejected = db_session.query(RejectedEntity).filter(
        RejectedEntity.vertical_id == vertical.id,
        RejectedEntity.entity_type == EntityType.BRAND,
        RejectedEntity.name == "BrandB",
    ).first()
    product_rejected = db_session.query(RejectedEntity).filter(
        RejectedEntity.vertical_id == vertical.id,
        RejectedEntity.entity_type == EntityType.PRODUCT,
        RejectedEntity.name == "ProductY",
    ).first()

    assert brand_rejected is not None
    assert product_rejected is not None
    assert brand_rejected.rejection_reason == "rejected_at_list_filter"
    assert product_rejected.rejection_reason == "rejected_at_list_filter"
