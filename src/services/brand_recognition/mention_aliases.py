from __future__ import annotations

from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from models import Vertical
from models.knowledge_domain import (
    KnowledgeBrand,
    KnowledgeBrandAlias,
    KnowledgeProduct,
    KnowledgeProductAlias,
)
from services.canonicalization_metrics import normalize_entity_key
from services.knowledge_session import knowledge_session
from services.knowledge_verticals import resolve_knowledge_vertical_id


def load_validated_knowledge_aliases(
    db: Session,
    vertical_id: int,
) -> Tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    vertical_name = _vertical_name(db, vertical_id)
    if not vertical_name:
        return {}, {}
    with knowledge_session(write=False) as knowledge_db:
        canonical_id = resolve_knowledge_vertical_id(knowledge_db, vertical_name)
        if not canonical_id:
            return {}, {}
        return _brand_alias_map(knowledge_db, int(canonical_id)), _product_alias_map(knowledge_db, int(canonical_id))


def _vertical_name(db: Session, vertical_id: int) -> str:
    row = db.query(Vertical).filter(Vertical.id == vertical_id).first()
    return (row.name or "").strip() if row else ""


def _brand_alias_map(knowledge_db: Session, vertical_id: int) -> Dict[str, List[str]]:
    rows = knowledge_db.query(KnowledgeBrand.id, KnowledgeBrand.canonical_name, KnowledgeBrand.display_name).filter(
        KnowledgeBrand.vertical_id == vertical_id,
        KnowledgeBrand.is_validated.is_(True),
    ).all()
    return _alias_map(knowledge_db, rows, KnowledgeBrandAlias.brand_id, KnowledgeBrandAlias.alias)


def _product_alias_map(knowledge_db: Session, vertical_id: int) -> Dict[str, List[str]]:
    rows = knowledge_db.query(KnowledgeProduct.id, KnowledgeProduct.canonical_name, KnowledgeProduct.display_name).filter(
        KnowledgeProduct.vertical_id == vertical_id,
        KnowledgeProduct.is_validated.is_(True),
    ).all()
    return _alias_map(knowledge_db, rows, KnowledgeProductAlias.product_id, KnowledgeProductAlias.alias)


def _alias_map(knowledge_db: Session, rows: list[tuple], id_col, alias_col) -> Dict[str, List[str]]:
    ids = [int(r[0]) for r in rows]
    if not ids:
        return {}
    alias_rows = knowledge_db.query(id_col, alias_col).filter(id_col.in_(ids)).all()
    by_id: dict[int, list[str]] = {}
    for entity_id, alias in alias_rows:
        by_id.setdefault(int(entity_id), []).append(str(alias or "").strip())
    result: Dict[str, List[str]] = {}
    for entity_id, canonical, display in rows:
        variants = _uniq([v for v in by_id.get(int(entity_id), []) if v])
        _set_aliases(result, canonical, variants)
        _set_aliases(result, display, variants)
    return result


def _set_aliases(target: Dict[str, List[str]], name: str, aliases: List[str]) -> None:
    if not name or not aliases:
        return
    key = normalize_entity_key(name)
    if key and key not in target:
        target[key] = aliases


def _uniq(values: List[str]) -> List[str]:
    seen, out = set(), []
    for v in values:
        if v in seen:
            continue
        seen.add(v)
        out.append(v)
    return out
