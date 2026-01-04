import re

from sqlalchemy import func
from sqlalchemy.orm import Session

from models.knowledge_domain import KnowledgeVertical, KnowledgeVerticalAlias


def resolve_knowledge_vertical_id(db: Session, name: str) -> int | None:
    alias = _find_alias(db, normalize_entity_key(name))
    if alias:
        return alias.vertical_id
    vertical = _find_vertical(db, name)
    return vertical.id if vertical else None


def get_or_create_vertical(db: Session, name: str) -> KnowledgeVertical:
    vertical = _find_vertical(db, name)
    if vertical:
        return vertical
    vertical = KnowledgeVertical(name=name.strip())
    db.add(vertical)
    db.flush()
    return vertical


def ensure_vertical_alias(db: Session, vertical_id: int, alias: str) -> None:
    alias_key = normalize_entity_key(alias)
    if _find_alias(db, alias_key):
        return
    db.add(KnowledgeVerticalAlias(vertical_id=vertical_id, alias=alias, alias_key=alias_key))


def _find_alias(db: Session, alias_key: str) -> KnowledgeVerticalAlias | None:
    return db.query(KnowledgeVerticalAlias).filter(
        KnowledgeVerticalAlias.alias_key == alias_key
    ).first()


def _find_vertical(db: Session, name: str) -> KnowledgeVertical | None:
    return db.query(KnowledgeVertical).filter(
        func.lower(KnowledgeVertical.name) == name.casefold()
    ).first()


def normalize_entity_key(text: str) -> str:
    cleaned = _drop_parenthetical((text or "").strip())
    cleaned = re.sub(r"[\s\W_]+", "", cleaned, flags=re.UNICODE)
    return cleaned.casefold()


def _drop_parenthetical(text: str) -> str:
    text = re.sub(r"\(.*?\)", "", text)
    return re.sub(r"（.*?）", "", text)
