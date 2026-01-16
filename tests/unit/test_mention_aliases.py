from sqlalchemy.orm import Session

from models import Vertical
from models.knowledge_domain import KnowledgeBrand, KnowledgeBrandAlias, KnowledgeProduct, KnowledgeProductAlias, KnowledgeVertical
from services.brand_recognition.mention_aliases import load_validated_knowledge_aliases
from services.canonicalization_metrics import normalize_entity_key
from services.knowledge_session import knowledge_session


def test_load_validated_knowledge_aliases_returns_maps(db_session: Session):
    vertical = Vertical(name="Cars", description=None)
    db_session.add(vertical)
    db_session.flush()

    with knowledge_session(write=True) as knowledge_db:
        kvert = KnowledgeVertical(name="Cars", description=None)
        knowledge_db.add(kvert)
        knowledge_db.flush()
        brand = KnowledgeBrand(vertical_id=kvert.id, canonical_name="BYD", display_name="BYD", is_validated=True)
        product = KnowledgeProduct(vertical_id=kvert.id, canonical_name="宋PLUS", display_name="宋PLUS", is_validated=True)
        knowledge_db.add_all([brand, product])
        knowledge_db.flush()
        knowledge_db.add(KnowledgeBrandAlias(brand_id=brand.id, alias="BYD Auto", language="en"))
        knowledge_db.add(KnowledgeProductAlias(product_id=product.id, alias="宋 PLUS", language="zh"))

    brand_map, product_map = load_validated_knowledge_aliases(db_session, vertical.id)
    assert "BYD Auto" in (brand_map.get(normalize_entity_key("BYD")) or [])
    assert "宋 PLUS" in (product_map.get(normalize_entity_key("宋PLUS")) or [])

