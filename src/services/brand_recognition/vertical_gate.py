import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy.orm import Session

from models import Brand, BrandMention, EntityType, LLMAnswer, Product, ProductMention, Prompt, RejectedEntity, Run
from models.domain import Sentiment
from services.brand_recognition.prompts import load_prompt
from services.ollama import OllamaService


@dataclass(frozen=True)
class _Evidence:
    prompt: str
    snippet: str


@dataclass
class _BrandEvidence:
    brand_id: int
    brand_name: str
    original_name: str
    evidence: List[_Evidence]


async def apply_vertical_gate_to_run(db: Session, run_id: int) -> int:
    """Mark discovered off-vertical brands (and linked products) as not mentioned for a run."""
    run = _get_run(db, run_id)
    brands = _gather_discovered_brand_evidence(db, run_id, run.vertical_id)
    if not brands:
        return 0
    rejected = await _classify_and_reject(run, list(brands.values()))
    _apply_rejections(db, run_id, rejected, run.vertical_id)
    return len(rejected)


def _get_run(db: Session, run_id: int) -> Run:
    run = db.query(Run).filter(Run.id == run_id).first()
    if not run:
        raise ValueError(f"Run {run_id} not found")
    return run


def _gather_discovered_brand_evidence(
    db: Session,
    run_id: int,
    vertical_id: int,
    max_mentions_per_brand: int = 3,
) -> Dict[int, _BrandEvidence]:
    mentions = _load_discovered_mentions(db, run_id, vertical_id)
    grouped = _group_mentions_by_brand(mentions, max_mentions_per_brand)
    return {bid: _brand_evidence(db, bid, vertical_id, ms) for bid, ms in grouped.items()}


def _load_discovered_mentions(db: Session, run_id: int, vertical_id: int) -> List[BrandMention]:
    return (_discovered_mentions_query(db, run_id, vertical_id)).all()


def _discovered_mentions_query(db: Session, run_id: int, vertical_id: int):
    return (db.query(BrandMention).join(Brand, Brand.id == BrandMention.brand_id).join(
        LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id
    ).filter(LLMAnswer.run_id == run_id, Brand.vertical_id == vertical_id, Brand.is_user_input == False, BrandMention.mentioned == True))


def _group_mentions_by_brand(
    mentions: Sequence[BrandMention],
    max_mentions_per_brand: int,
) -> Dict[int, List[BrandMention]]:
    grouped: Dict[int, List[BrandMention]] = {}
    for m in mentions:
        grouped.setdefault(m.brand_id, [])
        if len(grouped[m.brand_id]) < max_mentions_per_brand:
            grouped[m.brand_id].append(m)
    return grouped


def _brand_evidence(
    db: Session,
    brand_id: int,
    vertical_id: int,
    mentions: Sequence[BrandMention],
) -> _BrandEvidence:
    brand = _load_brand(db, brand_id, vertical_id)
    evidence = _compact_evidence(mentions)
    return _BrandEvidence(brand_id=brand_id, brand_name=_brand_label(brand, brand_id), original_name=_brand_original(brand, brand_id), evidence=evidence)


def _load_brand(db: Session, brand_id: int, vertical_id: int) -> Optional[Brand]:
    return db.query(Brand).filter(Brand.id == brand_id, Brand.vertical_id == vertical_id).first()


def _compact_evidence(mentions: Sequence[BrandMention]) -> List[_Evidence]:
    evidence = [_evidence_from_mention(m) for m in mentions]
    return [e for e in evidence if e is not None]


def _brand_label(brand: Optional[Brand], brand_id: int) -> str:
    return brand.display_name if brand else str(brand_id)


def _brand_original(brand: Optional[Brand], brand_id: int) -> str:
    return (brand.original_name if brand else str(brand_id)).strip()


def _evidence_from_mention(mention: BrandMention) -> Optional[_Evidence]:
    prompt_text = _prompt_text(mention.llm_answer.prompt)
    snippet = _first_snippet(mention.evidence_snippets)
    if not prompt_text or not snippet:
        return None
    return _Evidence(prompt=_truncate(prompt_text, 240), snippet=_truncate(snippet, 240))


def _prompt_text(prompt: Prompt) -> str:
    return (prompt.text_zh or prompt.text_en or "").strip()


def _first_snippet(evidence_snippets: Dict[str, Any]) -> str:
    snippets = (evidence_snippets or {}).get("zh") or []
    return (snippets[0] or "").strip() if snippets else ""


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rstrip()


async def _classify_and_reject(run: Run, brands: Sequence[_BrandEvidence]) -> List[_BrandEvidence]:
    results = await _classify_in_batches(run, brands)
    return [b for b in brands if results.get(b.original_name) is False]


async def _classify_in_batches(run: Run, brands: Sequence[_BrandEvidence]) -> Dict[str, Optional[bool]]:
    batches = _chunk(list(brands), 30)
    parsed: Dict[str, Optional[bool]] = {}
    for batch in batches:
        parsed.update(await _classify_batch(run, batch))
    return parsed


def _chunk(items: List[Any], size: int) -> List[List[Any]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


async def _classify_batch(run: Run, brands: Sequence[_BrandEvidence]) -> Dict[str, Optional[bool]]:
    candidates_json = _candidates_json(brands)
    response = await _call_vertical_gate_llm(run, candidates_json)
    return _parse_vertical_gate_response(response)


def _candidates_json(brands: Sequence[_BrandEvidence]) -> str:
    payload = [{"brand": b.original_name, "evidence": [e.__dict__ for e in b.evidence]} for b in brands]
    return json.dumps(payload, ensure_ascii=False)


async def _call_vertical_gate_llm(run: Run, candidates_json: str) -> str:
    ollama = _ollama_ner_client()
    system_prompt = load_prompt(
        "brand_vertical_relevance_system_prompt",
        vertical=run.vertical.name,
        vertical_description=run.vertical.description or "",
    )
    prompt = load_prompt("brand_vertical_relevance_user_prompt", candidates_json=candidates_json)
    return await ollama._call_ollama(model=ollama.ner_model, prompt=prompt, system_prompt=system_prompt, temperature=0.0)


def _ollama_ner_client() -> OllamaService:
    from src.config import settings

    client = OllamaService.__new__(OllamaService)
    client.base_url = settings.ollama_base_url
    client.ner_model = settings.ollama_model_ner
    return client


def _parse_vertical_gate_response(response: str) -> Dict[str, Optional[bool]]:
    data = _parse_json_object(response)
    results = (data or {}).get("results") or []
    if not isinstance(results, list):
        return {}
    return {_result_name(r): _result_relevant(r) for r in results if _result_name(r)}


def _parse_json_object(response: str) -> Dict[str, Any]:
    raw = _strip_code_fences((response or "").strip())
    if (obj := _find_json_object(raw)) is None:
        return {}
    return _loads_json(obj)


def _strip_code_fences(text: str) -> str:
    text = text[7:] if text.startswith("```json") else text
    text = text[3:] if text.startswith("```") else text
    text = text[:-3] if text.endswith("```") else text
    return text.strip()


def _find_json_object(text: str) -> Optional[str]:
    import re

    match = re.search(r"\{[\s\S]*\}", text)
    return match.group(0) if match else None


def _loads_json(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {}


def _result_name(result: Any) -> str:
    return (result.get("brand") if isinstance(result, dict) else "") or ""


def _result_relevant(result: Any) -> Optional[bool]:
    if not isinstance(result, dict):
        return None
    relevant = result.get("relevant")
    return bool(relevant) if relevant in [True, False] else None


def _apply_rejections(db: Session, run_id: int, rejected: Sequence[_BrandEvidence], vertical_id: int) -> None:
    brand_ids = [b.brand_id for b in rejected]
    if not brand_ids:
        return
    _mark_brand_mentions_off(db, run_id, brand_ids)
    _mark_linked_product_mentions_off(db, run_id, brand_ids)
    _store_off_vertical_rejections(db, vertical_id, rejected)


def _mark_brand_mentions_off(db: Session, run_id: int, brand_ids: Sequence[int]) -> None:
    for m in _brand_mentions(db, run_id, brand_ids):
        _mark_mention_off(m)


def _mark_linked_product_mentions_off(db: Session, run_id: int, brand_ids: Sequence[int]) -> None:
    for m in _product_mentions(db, run_id, brand_ids):
        _mark_mention_off(m)


def _mark_mention_off(mention: Any) -> None:
    mention.mentioned = False
    mention.rank = None
    mention.sentiment = Sentiment.NEUTRAL


def _brand_mentions(db: Session, run_id: int, brand_ids: Sequence[int]) -> List[BrandMention]:
    return (
        db.query(BrandMention)
        .join(LLMAnswer, LLMAnswer.id == BrandMention.llm_answer_id)
        .filter(LLMAnswer.run_id == run_id, BrandMention.brand_id.in_(brand_ids))
        .all()
    )


def _product_mentions(db: Session, run_id: int, brand_ids: Sequence[int]) -> List[ProductMention]:
    return (
        db.query(ProductMention)
        .join(LLMAnswer, LLMAnswer.id == ProductMention.llm_answer_id)
        .join(Product, Product.id == ProductMention.product_id)
        .filter(LLMAnswer.run_id == run_id, Product.brand_id.in_(brand_ids))
        .all()
    )


def _store_off_vertical_rejections(db: Session, vertical_id: int, rejected: Sequence[_BrandEvidence]) -> None:
    for b in rejected:
        if not b.original_name:
            continue
        _add_rejected_entity(db, vertical_id, b.original_name, _example_context(b))


def _example_context(brand: _BrandEvidence) -> str:
    if not brand.evidence:
        return ""
    e = brand.evidence[0]
    return json.dumps({"prompt": e.prompt, "snippet": e.snippet}, ensure_ascii=False)


def _add_rejected_entity(db: Session, vertical_id: int, name: str, context: str) -> None:
    if _rejection_exists(db, vertical_id, name):
        return
    db.add(_off_vertical_rejection(vertical_id, name, context))


def _rejection_exists(db: Session, vertical_id: int, name: str) -> bool:
    return bool(db.query(RejectedEntity).filter(
        RejectedEntity.vertical_id == vertical_id,
        RejectedEntity.entity_type == EntityType.BRAND,
        RejectedEntity.name == name,
        RejectedEntity.rejection_reason == "off_vertical",
    ).first())


def _off_vertical_rejection(vertical_id: int, name: str, context: str) -> RejectedEntity:
    return RejectedEntity(
        vertical_id=vertical_id,
        entity_type=EntityType.BRAND,
        name=name,
        rejection_reason="off_vertical",
        example_context=context or None,
    )
