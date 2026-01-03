from sqlalchemy.orm import Session

from models import Brand, Vertical
from services.brand_recognition.extraction_augmentation import get_validated_entity_names


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
