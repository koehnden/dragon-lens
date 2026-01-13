from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from sqlalchemy.orm import Session, selectinload

from models import (
    BrandMention,
    LLMAnswer,
    ProductBrandMapping,
    ProductMention,
    Run,
    RunStatus,
    Vertical,
)


def build_run_inspector_export(db: Session, run_id: int) -> list[dict[str, Any]]:
    run = _run_with_vertical(db, run_id)
    if not run:
        return []
    answers = _answers_for_run(db, run_id)
    return _items_from_answers(db, answers, run.vertical.name, run.vertical_id)


def build_vertical_inspector_export(db: Session, vertical_id: int) -> list[dict[str, Any]]:
    vertical = _vertical(db, vertical_id)
    if not vertical:
        return []
    answers = _answers_for_vertical(db, vertical_id)
    return _items_from_answers(db, answers, vertical.name, vertical_id)


def _run_with_vertical(db: Session, run_id: int) -> Run | None:
    return (
        db.query(Run)
        .options(selectinload(Run.vertical))
        .filter(Run.id == run_id)
        .first()
    )


def _vertical(db: Session, vertical_id: int) -> Vertical | None:
    return db.query(Vertical).filter(Vertical.id == vertical_id).first()


def _answers_for_run(db: Session, run_id: int) -> list[LLMAnswer]:
    return (
        db.query(LLMAnswer)
        .options(_answer_load_options())
        .filter(LLMAnswer.run_id == run_id)
        .order_by(LLMAnswer.prompt_id.asc(), LLMAnswer.id.asc())
        .all()
    )


def _answers_for_vertical(db: Session, vertical_id: int) -> list[LLMAnswer]:
    return (
        db.query(LLMAnswer)
        .join(Run, LLMAnswer.run_id == Run.id)
        .options(_answer_load_options())
        .filter(Run.vertical_id == vertical_id, Run.status == RunStatus.COMPLETED)
        .order_by(Run.run_time.desc(), LLMAnswer.prompt_id.asc(), LLMAnswer.id.asc())
        .all()
    )


def _answer_load_options():
    return (
        selectinload(LLMAnswer.prompt),
        selectinload(LLMAnswer.mentions).selectinload(BrandMention.brand),
        selectinload(LLMAnswer.product_mentions).selectinload(ProductMention.product),
    )


def _items_from_answers(
    db: Session,
    answers: list[LLMAnswer],
    vertical_name: str,
    vertical_id: int,
) -> list[dict[str, Any]]:
    product_map = _product_brand_map(db, vertical_id, _product_ids(answers))
    return [_item(answer, vertical_name, product_map) for answer in answers]


def _product_ids(answers: Iterable[LLMAnswer]) -> set[int]:
    ids: set[int] = set()
    for answer in answers:
        ids.update(_mentioned_product_ids(answer))
    return ids


def _mentioned_product_ids(answer: LLMAnswer) -> set[int]:
    return {m.product_id for m in answer.product_mentions if m.mentioned}


def _product_brand_map(db: Session, vertical_id: int, product_ids: set[int]) -> dict[int, int]:
    if not product_ids:
        return {}
    rows = _product_brand_rows(db, vertical_id, product_ids)
    return _first_mapping_per_product(rows)


def _product_brand_rows(
    db: Session, vertical_id: int, product_ids: set[int]
) -> list[ProductBrandMapping]:
    return (
        db.query(ProductBrandMapping)
        .filter(
            ProductBrandMapping.vertical_id == vertical_id,
            ProductBrandMapping.product_id.in_(product_ids),
            ProductBrandMapping.brand_id.isnot(None),
        )
        .order_by(
            ProductBrandMapping.is_validated.desc(),
            ProductBrandMapping.confidence.desc(),
            ProductBrandMapping.updated_at.desc(),
        )
        .all()
    )


def _first_mapping_per_product(rows: list[ProductBrandMapping]) -> dict[int, int]:
    mapped: dict[int, int] = {}
    for row in rows:
        if row.product_id not in mapped and row.brand_id is not None:
            mapped[row.product_id] = row.brand_id
    return mapped


def _item(answer: LLMAnswer, vertical_name: str, product_map: dict[int, int]) -> dict[str, Any]:
    prompt = answer.prompt
    return {
        "run_id": answer.run_id,
        "llm_answer_id": answer.id,
        "vertical_name": vertical_name,
        "model": answer.model_name,
        "prompt_zh": getattr(prompt, "text_zh", None),
        "prompt_eng": getattr(prompt, "text_en", None),
        "prompt_response_zh": answer.raw_answer_zh,
        "prompt_response_en": answer.raw_answer_en,
        "brands_extracted": _brands_extracted(answer, product_map),
    }


def _brands_extracted(answer: LLMAnswer, product_map: dict[int, int]) -> list[dict[str, Any]]:
    products_by_brand = _products_by_brand(answer, product_map)
    mentions = [m for m in answer.mentions if m.mentioned]
    mentions.sort(key=_mention_sort_key)
    return [_brand_item(m, products_by_brand.get(m.brand_id, [])) for m in mentions]


def _mention_sort_key(mention: BrandMention) -> tuple[int, int]:
    return (1 if mention.rank is None else 0, mention.rank or 0)


def _products_by_brand(
    answer: LLMAnswer, product_map: dict[int, int]
) -> dict[int, list[tuple[str, str]]]:
    grouped: dict[int, list[tuple[str, str]]] = defaultdict(list)
    for mention in answer.product_mentions:
        _add_product(grouped, mention, product_map)
    return {k: _dedupe_products(v) for k, v in grouped.items()}


def _add_product(
    grouped: dict[int, list[tuple[str, str]]],
    mention: ProductMention,
    product_map: dict[int, int],
) -> None:
    if not mention.mentioned or not mention.product:
        return
    brand_id = mention.product.brand_id or product_map.get(mention.product_id)
    if brand_id:
        grouped[brand_id].append(_product_names(mention.product))


def _product_names(product) -> tuple[str, str]:
    return product.original_name, product.translated_name or product.original_name


def _dedupe_products(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen: set[tuple[str, str]] = set()
    result: list[tuple[str, str]] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def _brand_item(mention: BrandMention, products: list[tuple[str, str]]) -> dict[str, Any]:
    brand = mention.brand
    return {
        "brand_zh": getattr(brand, "original_name", None),
        "brand_en": getattr(brand, "translated_name", None),
        "text_snippet_zh": _first_snippet(mention.evidence_snippets, "zh"),
        "text_snippet_en": _first_snippet(mention.evidence_snippets, "en"),
        "rank": mention.rank,
        "products_zh": [p[0] for p in products],
        "products_en": [p[1] for p in products],
    }


def _first_snippet(evidence: dict | None, lang: str) -> str | None:
    snippets = (evidence or {}).get(lang) or []
    first = snippets[0].strip() if snippets and snippets[0] else ""
    return first or None

