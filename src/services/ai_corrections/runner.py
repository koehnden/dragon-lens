from __future__ import annotations

from typing import Any

from services.ai_corrections.audit import build_audit_prompt, parse_audit_response


async def run_audit_batches(
    llm_router,
    provider: str,
    model_name: str,
    vertical_name: str,
    items: list[dict[str, Any]],
    batch_size: int = 5,
) -> tuple[list[dict[str, Any]], int, int]:
    outputs: list[dict[str, Any]] = []
    tokens_in = 0
    tokens_out = 0
    for batch in _batches(items, batch_size):
        parsed, tin, tout = await _run_batch(llm_router, provider, model_name, vertical_name, batch)
        outputs.extend(parsed.get("items") or [])
        tokens_in += tin
        tokens_out += tout
    return outputs, tokens_in, tokens_out


def _batches(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i:i + size] for i in range(0, len(items), size)]


async def _run_batch(
    llm_router,
    provider: str,
    model_name: str,
    vertical_name: str,
    batch: list[dict[str, Any]],
) -> tuple[dict[str, Any], int, int]:
    prompt = build_audit_prompt(vertical_name, batch)
    answer, tokens_in, tokens_out, _, _ = await llm_router.query(provider, model_name, prompt)
    return parse_audit_response(answer), int(tokens_in or 0), int(tokens_out or 0)

