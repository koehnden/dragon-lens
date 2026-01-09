from __future__ import annotations

from sqlalchemy.orm import Session

from models import Brand, Product
from models.domain import EntityType
from models.knowledge_domain import KnowledgeTranslationOverride
from services.knowledge_examples import translation_override_examples
from services.knowledge_session import knowledge_session
from services.knowledge_verticals import resolve_knowledge_vertical_id
from services.translater import TranslaterService, has_chinese_characters, has_latin_letters


def apply_translation_feedback(
    db: Session,
    vertical_name: str,
    vertical_description: str | None,
    brands: list[Brand],
    products: list[Product],
) -> None:
    with knowledge_session() as knowledge_db:
        knowledge_id = resolve_knowledge_vertical_id(knowledge_db, vertical_name) if vertical_name else None
        _apply_type(db, knowledge_db, knowledge_id, "brand", brands, vertical_name, vertical_description)
        _apply_type(db, knowledge_db, knowledge_id, "product", products, vertical_name, vertical_description)


def _apply_type(
    db: Session,
    knowledge_db: Session,
    knowledge_id: int | None,
    kind: str,
    items: list,
    vertical_name: str,
    vertical_description: str | None,
) -> None:
    entity_type = EntityType.BRAND if kind == "brand" else EntityType.PRODUCT
    overrides = _override_map(knowledge_db, knowledge_id, entity_type)
    examples = translation_override_examples(knowledge_db, knowledge_id, entity_type, limit=30, language="en")
    pending = _apply_overrides(items, overrides)
    _apply_llm_translations(db, kind, items, pending, vertical_name, vertical_description, examples)


def _override_map(db: Session, knowledge_id: int | None, entity_type: EntityType) -> dict[str, str]:
    if not knowledge_id:
        return {}
    rows = db.query(KnowledgeTranslationOverride).filter(
        KnowledgeTranslationOverride.vertical_id == knowledge_id,
        KnowledgeTranslationOverride.entity_type == entity_type,
        KnowledgeTranslationOverride.language == "en",
    ).all()
    return {row.canonical_name.casefold(): row.override_text for row in rows if row.canonical_name and row.override_text}


def _apply_overrides(items: list, overrides: dict[str, str]) -> set[str]:
    pending: set[str] = set()
    for item in items:
        name = _source_name(item)
        if not name:
            continue
        if _apply_override(item, overrides, name):
            continue
        if _should_translate(item, name):
            pending.add(name)
    return pending


def _apply_llm_translations(
    db: Session,
    kind: str,
    items: list,
    pending: set[str],
    vertical_name: str,
    vertical_description: str | None,
    examples: list[dict],
) -> None:
    if not pending:
        return
    translator = TranslaterService()
    results = translator.translate_entities_to_english_batch_sync(
        _payload(kind, pending), vertical_name, vertical_description, override_examples=examples
    )
    _apply_results(kind, items, results)
    db.flush()


def _needs_english(name: str) -> bool:
    if not has_chinese_characters(name):
        return False
    return not has_latin_letters(name)


def _source_name(item) -> str:
    return (getattr(item, "original_name", "") or "").strip()


def _apply_override(item, overrides: dict[str, str], name: str) -> bool:
    override = overrides.get(name.casefold())
    if not override:
        return False
    item.translated_name = override
    return True


def _should_translate(item, name: str) -> bool:
    if not _needs_english(name):
        return False
    return not (getattr(item, "translated_name", "") or "").strip()


def _payload(kind: str, names: set[str]) -> list[dict]:
    return [{"type": kind, "name": name} for name in sorted(names)]


def _apply_results(kind: str, items: list, results: dict[tuple[str, str], str]) -> None:
    for item in items:
        name = _source_name(item)
        english = results.get((kind, name))
        if english:
            item.translated_name = english
