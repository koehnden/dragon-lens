from __future__ import annotations

from collections import defaultdict
from typing import Any

from services.ai_corrections.audit import key_set, mapping_key_set
from services.ai_corrections.metrics import compute_metrics
from services.ai_corrections.policy import AICorrectionThresholds, MinConfidenceLevels
from services.ai_corrections.suggestions import feedback_payload, split_suggestions


def build_report(
    run_export: list[dict[str, Any]],
    audit_items: list[dict[str, Any]],
    thresholds: AICorrectionThresholds,
    min_levels: MinConfidenceLevels,
    run_id: int,
    canonical_vertical_id: int,
    vertical_id: int,
) -> dict[str, Any]:
    export_by_answer = {int(i["llm_answer_id"]): i for i in run_export}
    matched = [(a, export_by_answer.get(int(a.get("llm_answer_id") or 0))) for a in audit_items]
    matched = [(a, e) for a, e in matched if e]
    return _report(matched, thresholds, min_levels, run_id, canonical_vertical_id, vertical_id)


def _report(
    items: list[tuple[dict[str, Any], dict[str, Any]]],
    thresholds: AICorrectionThresholds,
    min_levels: MinConfidenceLevels,
    run_id: int,
    canonical_vertical_id: int,
    vertical_id: int,
) -> dict[str, Any]:
    metrics = _all_metrics(items)
    auto, review = _split_all(items, thresholds, min_levels)
    clusters = _clusters(auto + review)
    return {
        "metrics": metrics,
        "clusters": clusters,
        "auto_suggestions": auto,
        "review_suggestions": _review_items(review, run_id, vertical_id, canonical_vertical_id),
    }


def _all_metrics(items: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    brand = _metric_sum(items, _truth_brands, _pred_brands)
    product = _metric_sum(items, _truth_products, _pred_products)
    mapping = _metric_sum(items, _truth_mappings, _pred_mappings)
    return {"brands": brand, "products": product, "mappings": mapping}


def _metric_sum(items, truth_fn, pred_fn) -> dict:
    tp = fp = fn = 0
    for audit_item, export_item in items:
        a, b, c = _counts(truth_fn(audit_item), pred_fn(export_item))
        tp += a
        fp += b
        fn += c
    return compute_metrics(tp, fp, fn)


def _counts(truth: set, pred: set) -> tuple[int, int, int]:
    tp = len(truth & pred)
    fp = len(pred - truth)
    fn = len(truth - pred)
    return tp, fp, fn


def _truth_brands(audit_item: dict[str, Any]) -> set[str]:
    return key_set(((audit_item.get("truth") or {}).get("brands") or []))


def _pred_brands(export_item: dict[str, Any]) -> set[str]:
    names = [_brand_name(b) for b in (export_item.get("brands_extracted") or [])]
    return key_set([n for n in names if n])


def _brand_name(item: dict[str, Any]) -> str:
    return (item.get("brand_zh") or item.get("brand_en") or "").strip()


def _truth_products(audit_item: dict[str, Any]) -> set[str]:
    return key_set(((audit_item.get("truth") or {}).get("products") or []))


def _pred_products(export_item: dict[str, Any]) -> set[str]:
    products: list[str] = []
    for brand in export_item.get("brands_extracted") or []:
        products.extend(brand.get("products_zh") or [])
    return key_set(products)


def _truth_mappings(audit_item: dict[str, Any]) -> set[tuple[str, str]]:
    return mapping_key_set(((audit_item.get("truth") or {}).get("mappings") or []))


def _pred_mappings(export_item: dict[str, Any]) -> set[tuple[str, str]]:
    pairs: list[dict[str, str]] = []
    for brand in export_item.get("brands_extracted") or []:
        b = _brand_name(brand)
        for product in brand.get("products_zh") or []:
            pairs.append({"product": product, "brand": b})
    return mapping_key_set(pairs)


def _split_all(items, thresholds, min_levels) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    auto: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for audit_item, export_item in items:
        a, r = split_suggestions(
            audit_item.get("suggestions") or [],
            export_item.get("prompt_response_zh") or "",
            thresholds,
            min_levels,
        )
        auto.extend(_attach_ids(audit_item, export_item, a))
        review.extend(_attach_ids(audit_item, export_item, r))
    return auto, review


def _attach_ids(
    audit_item: dict[str, Any],
    export_item: dict[str, Any],
    suggestions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    llm_answer_id = int(audit_item.get("llm_answer_id") or 0)
    return [{**s, "llm_answer_id": llm_answer_id, "run_id": int(export_item.get("run_id") or 0)} for s in suggestions]


def _clusters(suggestions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[int]] = defaultdict(list)
    for s in suggestions:
        grouped[(s.get("category") or "Uncategorized")].append(int(s.get("llm_answer_id") or 0))
    return [{"category": k, "count": len(v), "examples": [str(i) for i in v[:2] if i]} for k, v in grouped.items()]


def auto_feedback_payload(run_id: int, vertical_id: int, canonical_vertical_id: int, suggestions: list[dict[str, Any]]) -> dict:
    return feedback_payload(run_id, vertical_id, canonical_vertical_id, suggestions)


def _review_items(suggestions: list[dict[str, Any]], run_id: int, vertical_id: int, canonical_vertical_id: int) -> list[dict[str, Any]]:
    return [_review_item(s, run_id, vertical_id, canonical_vertical_id) for s in suggestions]


def _review_item(suggestion: dict[str, Any], run_id: int, vertical_id: int, canonical_vertical_id: int) -> dict[str, Any]:
    suggestion_run_id = int(suggestion.get("run_id") or run_id or 0)
    payload = feedback_payload(suggestion_run_id, vertical_id, canonical_vertical_id, [suggestion])
    return {
        "run_id": suggestion_run_id,
        "llm_answer_id": int(suggestion.get("llm_answer_id") or 0),
        "category": suggestion.get("category") or "",
        "action": suggestion.get("action") or "",
        "confidence_level": suggestion.get("confidence_level") or "",
        "confidence_score": float(suggestion.get("confidence_score_0_1") or 0.0),
        "reason": suggestion.get("reason") or "",
        "evidence_quote_zh": suggestion.get("evidence_quote_zh"),
        "feedback_payload": payload,
    }
