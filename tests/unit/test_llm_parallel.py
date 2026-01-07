import asyncio

import pytest


@pytest.mark.asyncio
async def test_fetch_llm_answers_parallel_respects_concurrency():
    from workers.llm_parallel import LLMRequest, fetch_llm_answers_parallel

    current = 0
    max_seen = 0
    lock = asyncio.Lock()

    async def query_fn(prompt_zh: str):
        nonlocal current, max_seen
        async with lock:
            current += 1
            max_seen = max(max_seen, current)
        await asyncio.sleep(0.02)
        async with lock:
            current -= 1
        return "ok", 1, 2, 0.3

    requests = [LLMRequest(prompt_id=i, prompt_text_zh=f"p{i}") for i in range(10)]
    results = await fetch_llm_answers_parallel(requests, query_fn, concurrency=3)

    assert len(results) == 10
    assert max_seen <= 3
    assert max_seen >= 2


@pytest.mark.asyncio
async def test_fetch_llm_answers_parallel_returns_errors_inline():
    from workers.llm_parallel import LLMRequest, fetch_llm_answers_parallel

    async def query_fn(prompt_zh: str):
        if prompt_zh == "bad":
            raise ValueError("boom")
        return prompt_zh, 0, 0, 0.0

    requests = [
        LLMRequest(prompt_id=1, prompt_text_zh="ok"),
        LLMRequest(prompt_id=2, prompt_text_zh="bad"),
        LLMRequest(prompt_id=3, prompt_text_zh="ok2"),
    ]
    results = await fetch_llm_answers_parallel(requests, query_fn, concurrency=5)

    assert [r.prompt_id for r in results] == [1, 2, 3]
    assert results[0].answer_zh == "ok"
    assert results[1].error == "boom"
    assert results[2].answer_zh == "ok2"
