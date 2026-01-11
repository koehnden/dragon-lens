import json

from difflib import SequenceMatcher

from sqlalchemy import func
from sqlalchemy.orm import Session

from config import settings
from models import Brand, BrandMention, LLMAnswer, Product, ProductMention, Run, RunStatus, Vertical
from models.knowledge_domain import KnowledgeVertical, KnowledgeVerticalAlias
from services.brand_recognition.prompts import load_prompt
from services.brand_recognition.text_utils import _parse_json_response
from services.knowledge_session import knowledge_session
from services.knowledge_verticals import normalize_entity_key, resolve_knowledge_vertical_id
from services.ollama import OllamaService


async def ensure_vertical_grouping_for_run(db: Session, run_id: int) -> int | None:
    run = _run_or_none(db, run_id)
    if not run:
        return None
    vertical = db.query(Vertical).filter(Vertical.id == run.vertical_id).first()
    if not vertical:
        return None
    with knowledge_session(write=True) as knowledge_db:
        existing = resolve_knowledge_vertical_id(knowledge_db, vertical.name)
        if existing:
            _ensure_alias(knowledge_db, existing, vertical.name, "auto_existing")
            return int(existing)
        candidates = _candidate_names(knowledge_db, vertical.name, limit=settings.vertical_auto_match_max_candidates)
        sample = _sample_entities(db, run_id)
        decision = await _decide(vertical, candidates, sample)
        return _apply_decision(knowledge_db, vertical, candidates, decision)


def _run_or_none(db: Session, run_id: int) -> Run | None:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run or run.status == RunStatus.FAILED:
        return None
    return run


def _candidate_names(knowledge_db: Session, vertical_name: str, limit: int) -> list[str]:
    scored = _candidate_scores(knowledge_db, vertical_name)
    ranked = sorted(scored, key=lambda item: item[0], reverse=True)
    return [name for _, name in ranked[: max(1, limit)]]


def _candidate_scores(knowledge_db: Session, vertical_name: str) -> list[tuple[float, str]]:
    key = normalize_entity_key(vertical_name)
    names = _all_vertical_name_variants(knowledge_db)
    return [(max(_sim(key, normalize_entity_key(v)) for v in variants), canonical) for canonical, variants in names.items()]


def _all_vertical_name_variants(knowledge_db: Session) -> dict[str, list[str]]:
    rows = knowledge_db.query(KnowledgeVertical.id, KnowledgeVertical.name).all()
    by_id = {int(i): [n] for i, n in rows if n}
    for vid, alias in knowledge_db.query(KnowledgeVerticalAlias.vertical_id, KnowledgeVerticalAlias.alias).all():
        if alias and int(vid) in by_id:
            by_id[int(vid)].append(alias)
    return {variants[0]: variants for variants in by_id.values() if variants}


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _sample_entities(db: Session, run_id: int) -> dict:
    brands = _top_run_brands(db, run_id, limit=20)
    products = _top_run_products(db, run_id, limit=20)
    return {"brands": brands, "products": products}


def _top_run_brands(db: Session, run_id: int, limit: int) -> list[str]:
    rows = db.query(Brand.original_name, func.count(BrandMention.id)).join(
        BrandMention, BrandMention.brand_id == Brand.id
    ).join(
        LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id
    ).filter(
        LLMAnswer.run_id == run_id, BrandMention.mentioned
    ).group_by(Brand.original_name).order_by(func.count(BrandMention.id).desc()).limit(limit).all()
    return [name for name, _ in rows if (name or "").strip()]


def _top_run_products(db: Session, run_id: int, limit: int) -> list[str]:
    rows = db.query(Product.original_name, func.count(ProductMention.id)).join(
        ProductMention, ProductMention.product_id == Product.id
    ).join(
        LLMAnswer, LLMAnswer.id == ProductMention.llm_answer_id
    ).filter(
        LLMAnswer.run_id == run_id, ProductMention.mentioned
    ).group_by(Product.original_name).order_by(func.count(ProductMention.id).desc()).limit(limit).all()
    return [name for name, _ in rows if (name or "").strip()]


async def _decide(vertical: Vertical, candidates: list[str], sample: dict) -> dict:
    system = load_prompt("vertical_auto_match_system_prompt")
    prompt = load_prompt(
        "vertical_auto_match_prompt",
        vertical_name=vertical.name,
        vertical_description=vertical.description or "",
        candidate_verticals_json=_json(candidates),
        sample_entities_json=_json(sample),
        min_confidence=settings.vertical_auto_match_min_confidence,
    )
    response = await OllamaService()._call_ollama(
        model=settings.vertical_auto_match_model or settings.ollama_model_ner,
        prompt=prompt,
        system_prompt=system,
        temperature=0.0,
    )
    return _parse_json_response(response) or {}


def _apply_decision(knowledge_db: Session, vertical: Vertical, candidates: list[str], decision: dict) -> int | None:
    match = bool(decision.get("match"))
    confidence = float(decision.get("confidence") or 0.0)
    matched = (decision.get("matched_canonical_vertical_name") or "").strip()
    suggested = (decision.get("suggested_canonical_vertical_name") or "").strip()
    allowed = {c.casefold() for c in candidates if c}
    if match and confidence >= settings.vertical_auto_match_min_confidence and matched and matched.casefold() in allowed:
        canonical = _get_or_create_canonical(knowledge_db, matched, None)
        _ensure_alias(knowledge_db, canonical.id, vertical.name, "auto_qwen_match")
        return int(canonical.id)
    if suggested:
        canonical = _get_or_create_canonical(knowledge_db, suggested, (decision.get("suggested_description") or "").strip() or None)
        _ensure_alias(knowledge_db, canonical.id, vertical.name, "auto_qwen_created")
        return int(canonical.id)
    canonical = _get_or_create_canonical(knowledge_db, vertical.name, vertical.description)
    _ensure_alias(knowledge_db, canonical.id, vertical.name, "auto_fallback")
    return int(canonical.id)


def _get_or_create_canonical(knowledge_db: Session, name: str, description: str | None) -> KnowledgeVertical:
    row = knowledge_db.query(KnowledgeVertical).filter(func.lower(KnowledgeVertical.name) == name.casefold()).first()
    if row:
        if description and not (row.description or "").strip():
            row.description = description
        return row
    vertical = KnowledgeVertical(name=name.strip(), description=description or None)
    knowledge_db.add(vertical)
    knowledge_db.flush()
    return vertical


def _ensure_alias(knowledge_db: Session, vertical_id: int, alias: str, source: str) -> None:
    alias_key = normalize_entity_key(alias)
    exists = knowledge_db.query(KnowledgeVerticalAlias.id).filter(
        KnowledgeVerticalAlias.vertical_id == vertical_id, KnowledgeVerticalAlias.alias_key == alias_key
    ).first()
    if exists:
        return
    knowledge_db.add(KnowledgeVerticalAlias(vertical_id=vertical_id, alias=alias, alias_key=alias_key, source=source))


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)
