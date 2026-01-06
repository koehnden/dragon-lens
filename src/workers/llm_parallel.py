import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

QueryFn = Callable[[str], Awaitable[tuple[str, int, int, float]]]


@dataclass(frozen=True)
class LLMRequest:
    prompt_id: int
    prompt_text_zh: str


@dataclass(frozen=True)
class LLMResult:
    prompt_id: int
    answer_zh: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    latency: float = 0.0
    error: str | None = None


def _semaphore(concurrency: int) -> asyncio.Semaphore:
    return asyncio.Semaphore(max(1, concurrency))


async def _query_one(req: LLMRequest, query_fn: QueryFn, semaphore: asyncio.Semaphore):
    async with semaphore:
        return await query_fn(req.prompt_text_zh)


def _to_result(req: LLMRequest, raw: object) -> LLMResult:
    if isinstance(raw, Exception):
        return LLMResult(prompt_id=req.prompt_id, error=str(raw))
    answer_zh, tokens_in, tokens_out, latency = raw
    return LLMResult(req.prompt_id, answer_zh, tokens_in, tokens_out, latency)


async def fetch_llm_answers_parallel(
    requests: list[LLMRequest],
    query_fn: QueryFn,
    concurrency: int,
) -> list[LLMResult]:
    semaphore = _semaphore(concurrency)
    coros = [_query_one(r, query_fn, semaphore) for r in requests]
    results = await asyncio.gather(*coros, return_exceptions=True)
    return [_to_result(r, results[i]) for i, r in enumerate(requests)]
