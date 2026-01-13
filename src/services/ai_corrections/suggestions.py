from __future__ import annotations

from typing import Any

from models.schemas import (
    FeedbackBrandFeedbackItem,
    FeedbackMappingFeedbackItem,
    FeedbackProductFeedbackItem,
    FeedbackTranslationOverrideItem,
    FeedbackAction,
    FeedbackMappingAction,
    FeedbackSubmitRequest,
    FeedbackCanonicalVertical,
)
from services.ai_corrections.policy import (
    AICorrectionThresholds,
    ConfidenceLevel,
    MinConfidenceLevels,
    should_auto_apply,
)


def split_suggestions(
    suggestions: list[dict[str, Any]],
    prompt_response_zh: str,
    thresholds: AICorrectionThresholds,
    min_levels: MinConfidenceLevels,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    auto: list[dict[str, Any]] = []
    review: list[dict[str, Any]] = []
    for s in suggestions:
        (auto if _auto(s, prompt_response_zh, thresholds, min_levels) else review).append(s)
    return auto, review


def _auto(
    suggestion: dict[str, Any],
    prompt_response_zh: str,
    thresholds: AICorrectionThresholds,
    min_levels: MinConfidenceLevels,
) -> bool:
    return should_auto_apply(
        action=_policy_action(suggestion),
        confidence_level=_confidence_level(suggestion),
        confidence_score=float(suggestion.get("confidence_score_0_1") or 0.0),
        evidence_quote_zh=suggestion.get("evidence_quote_zh"),
        prompt_response_zh=prompt_response_zh,
        thresholds=thresholds,
        min_levels=min_levels,
    )


def _policy_action(suggestion: dict[str, Any]) -> str:
    action = (suggestion.get("action") or "").strip()
    if action.startswith("reject_"):
        return action
    if action.startswith("add_mapping"):
        return "add_mapping"
    if action.startswith("replace_"):
        return "replace"
    return "validate"


def _confidence_level(suggestion: dict[str, Any]) -> ConfidenceLevel:
    value = (suggestion.get("confidence_level") or "").strip().upper()
    return ConfidenceLevel(value) if value in ConfidenceLevel.__members__ else ConfidenceLevel.LOW


def feedback_payload(
    run_id: int,
    vertical_id: int,
    canonical_vertical_id: int,
    suggestions: list[dict[str, Any]],
) -> dict:
    request = FeedbackSubmitRequest(
        run_id=run_id,
        vertical_id=vertical_id,
        canonical_vertical=FeedbackCanonicalVertical(id=canonical_vertical_id, is_new=False),
        brand_feedback=_brand_feedback(suggestions),
        product_feedback=_product_feedback(suggestions),
        mapping_feedback=_mapping_feedback(suggestions),
        translation_overrides=[],
    )
    return request.model_dump()


def _brand_feedback(suggestions: list[dict[str, Any]]) -> list[FeedbackBrandFeedbackItem]:
    items = [s for s in suggestions if (s.get("action") or "").endswith("_brand")]
    return [_brand_item(i) for i in items if _brand_item(i) is not None]


def _brand_item(suggestion: dict[str, Any]) -> FeedbackBrandFeedbackItem | None:
    action = suggestion.get("action")
    if action == "validate_brand":
        return FeedbackBrandFeedbackItem(action=FeedbackAction.VALIDATE, name=suggestion.get("brand_name"), reason=suggestion.get("reason"))
    if action == "reject_brand":
        return FeedbackBrandFeedbackItem(action=FeedbackAction.REJECT, name=suggestion.get("brand_name"), reason=suggestion.get("reason"))
    if action == "replace_brand":
        return FeedbackBrandFeedbackItem(action=FeedbackAction.REPLACE, wrong_name=suggestion.get("wrong_name"), correct_name=suggestion.get("correct_name"), reason=suggestion.get("reason"))
    return None


def _product_feedback(suggestions: list[dict[str, Any]]) -> list[FeedbackProductFeedbackItem]:
    items = [s for s in suggestions if (s.get("action") or "").endswith("_product")]
    return [_product_item(i) for i in items if _product_item(i) is not None]


def _product_item(suggestion: dict[str, Any]) -> FeedbackProductFeedbackItem | None:
    action = suggestion.get("action")
    if action == "validate_product":
        return FeedbackProductFeedbackItem(action=FeedbackAction.VALIDATE, name=suggestion.get("product_name"), reason=suggestion.get("reason"))
    if action == "reject_product":
        return FeedbackProductFeedbackItem(action=FeedbackAction.REJECT, name=suggestion.get("product_name"), reason=suggestion.get("reason"))
    if action == "replace_product":
        return FeedbackProductFeedbackItem(action=FeedbackAction.REPLACE, wrong_name=suggestion.get("wrong_name"), correct_name=suggestion.get("correct_name"), reason=suggestion.get("reason"))
    return None


def _mapping_feedback(suggestions: list[dict[str, Any]]) -> list[FeedbackMappingFeedbackItem]:
    actions = {"add_mapping", "validate_mapping", "reject_mapping"}
    items = [s for s in suggestions if (s.get("action") or "") in actions]
    return [_mapping_item(i) for i in items if _mapping_item(i) is not None]


def _mapping_item(suggestion: dict[str, Any]) -> FeedbackMappingFeedbackItem | None:
    action = suggestion.get("action")
    if action == "add_mapping":
        return FeedbackMappingFeedbackItem(action=FeedbackMappingAction.ADD, product_name=suggestion.get("product_name"), brand_name=suggestion.get("brand_name"), reason=suggestion.get("reason"))
    if action == "validate_mapping":
        return FeedbackMappingFeedbackItem(action=FeedbackMappingAction.VALIDATE, product_name=suggestion.get("product_name"), brand_name=suggestion.get("brand_name"), reason=suggestion.get("reason"))
    if action == "reject_mapping":
        return FeedbackMappingFeedbackItem(action=FeedbackMappingAction.REJECT, product_name=suggestion.get("product_name"), brand_name=suggestion.get("brand_name"), reason=suggestion.get("reason"))
    return None

