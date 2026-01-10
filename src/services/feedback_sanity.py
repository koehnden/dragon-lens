import json

from config import settings
from models.schemas import FeedbackSubmitRequest
from services.brand_recognition.prompts import load_prompt
from services.brand_recognition.text_utils import _parse_json_response
from services.ollama import OllamaService


def _system_prompt() -> str:
    return load_prompt("feedback_sanity_system_prompt")


def _payload_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False)


def _reasons(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if str(v).strip()]


def _decision(data: dict | None) -> tuple[bool, list[str]]:
    if not data:
        return False, ["invalid_qwen_response"]
    accept = data.get("accept")
    reasons = _reasons(data.get("reasons"))
    if accept is True:
        return True, reasons
    if accept is False:
        return False, reasons or ["rejected"]
    return False, ["invalid_qwen_response"]


async def _check(prompt_id: str, vertical_name: str, **kwargs: object) -> tuple[bool, list[str]]:
    prompt = load_prompt(prompt_id, vertical_name=vertical_name, **kwargs)
    response = await OllamaService()._call_ollama(
        model=settings.ollama_model_ner,
        prompt=prompt,
        system_prompt=_system_prompt(),
        temperature=0.0,
    )
    return _decision(_parse_json_response(response))


async def check_brand_feedback(payload: FeedbackSubmitRequest, vertical_name: str) -> tuple[bool, list[str]]:
    return await _check(
        "feedback_brand_sanity_prompt",
        vertical_name,
        brand_feedback_json=_payload_json(payload.brand_feedback),
    )


async def check_product_feedback(payload: FeedbackSubmitRequest, vertical_name: str) -> tuple[bool, list[str]]:
    return await _check(
        "feedback_product_sanity_prompt",
        vertical_name,
        product_feedback_json=_payload_json(payload.product_feedback),
        mapping_feedback_json=_payload_json(payload.mapping_feedback),
    )


async def check_translation_feedback(payload: FeedbackSubmitRequest, vertical_name: str) -> tuple[bool, list[str]]:
    return await _check(
        "feedback_translation_sanity_prompt",
        vertical_name,
        translation_overrides_json=_payload_json(payload.translation_overrides),
    )
