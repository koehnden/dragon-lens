import logging
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from config import settings
from models import LLMAnswer, Prompt, Run
from models.db_retry import commit_with_retry, flush_with_retry
from models.domain import LLMRoute
from services.answer_reuse import find_reusable_answer
from services.brand_recognition.async_utils import _run_async
from services.pricing import calculate_cost
from services.remote_llms import LLMRouter
from services.translater import TranslaterService
from workers.llm_parallel import LLMRequest, LLMResult, fetch_llm_answers_parallel

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnswerTaskResult:
    run_id: int
    prompt_id: int
    llm_answer_id: int | None
    ok: bool
    reused: bool
    error: str | None = None

    def to_payload(self) -> dict:
        return {
            "run_id": self.run_id,
            "prompt_id": self.prompt_id,
            "llm_answer_id": self.llm_answer_id,
            "ok": self.ok,
            "reused": self.reused,
            "stage": "answer",
            "error": self.error,
        }


@dataclass(frozen=True)
class PromptWorkItem:
    prompt: Prompt
    prompt_text_zh: str
    prompt_text_en: str | None
    existing_answer: LLMAnswer | None
    reusable_answer: LLMAnswer | None


@dataclass(frozen=True)
class PreparedAnswer:
    item: PromptWorkItem
    llm_answer: LLMAnswer
    answer_zh: str


def _existing_answer(db: Session, run_id: int, prompt_id: int) -> LLMAnswer | None:
    return (
        db.query(LLMAnswer)
        .filter(LLMAnswer.run_id == run_id, LLMAnswer.prompt_id == prompt_id)
        .first()
    )


def _ensure_prompt_text_zh(prompt: Prompt, translator: TranslaterService) -> str | None:
    if prompt.text_zh:
        return prompt.text_zh
    if not prompt.text_en:
        return None
    return translator.translate_text_sync(prompt.text_en, "English", "Chinese")


def _prompt_text_zh(prompt: Prompt, translator: TranslaterService) -> str | None:
    if prompt.text_zh:
        return prompt.text_zh
    if not prompt.text_en:
        return None
    logger.info("Translating English prompt to Chinese: %s...", prompt.text_en[:50])
    return translator.translate_text_sync(prompt.text_en, "English", "Chinese")


def _answer_result(
    run_id: int,
    prompt_id: int,
    llm_answer_id: int | None,
    ok: bool,
    reused: bool,
    error: str | None = None,
) -> AnswerTaskResult:
    return AnswerTaskResult(run_id, prompt_id, llm_answer_id, ok, reused, error)


def _copy_reused_answer(
    db: Session, run_id: int, prompt_id: int, run: Run, reusable: LLMAnswer
) -> AnswerTaskResult:
    try:
        llm_answer = LLMAnswer(
            run_id=run_id,
            prompt_id=prompt_id,
            provider=run.provider,
            model_name=run.model_name,
            route=reusable.route,
            raw_answer_zh=reusable.raw_answer_zh,
            raw_answer_en=reusable.raw_answer_en,
            tokens_in=reusable.tokens_in,
            tokens_out=reusable.tokens_out,
            latency=reusable.latency,
            cost_estimate=reusable.cost_estimate,
        )
        db.add(llm_answer)
        flush_with_retry(db)
        commit_with_retry(db)
        return _answer_result(run_id, prompt_id, llm_answer.id, True, True)
    except IntegrityError:
        db.rollback()
        existing = _existing_answer(db, run_id, prompt_id)
        if not existing:
            return _answer_result(
                run_id, prompt_id, None, False, False, "IntegrityError on reused insert"
            )
        return _answer_result(run_id, prompt_id, existing.id, True, True)


def ensure_llm_answer_for_prompt(
    db: Session, run_id: int, prompt_id: int
) -> AnswerTaskResult:
    try:
        run = db.query(Run).filter(Run.id == run_id).first()
        prompt = (
            db.query(Prompt)
            .filter(Prompt.id == prompt_id, Prompt.run_id == run_id)
            .first()
        )
        if not run or not prompt:
            return _answer_result(
                run_id, prompt_id, None, False, False, "Run or prompt not found"
            )

        existing = _existing_answer(db, run_id, prompt_id)
        if existing:
            return _answer_result(run_id, prompt_id, existing.id, True, True)

        translator = TranslaterService()
        prompt_text_zh = _ensure_prompt_text_zh(prompt, translator)
        if not prompt_text_zh:
            return _answer_result(
                run_id, prompt_id, None, False, False, "Prompt has no text"
            )

        reusable = find_reusable_answer(
            db, run, prompt_text_zh=prompt_text_zh, prompt_text_en=prompt.text_en
        )
        if reusable:
            return _copy_reused_answer(db, run_id, prompt_id, run, reusable)

        llm_router = LLMRouter(db)
        resolution = llm_router.resolve(run.provider, run.model_name)
        answer_zh, tokens_in, tokens_out, latency = _run_async(
            llm_router.query_with_resolution(resolution, prompt_text_zh)
        )
        answer_en = (
            translator.translate_text_sync(answer_zh, "Chinese", "English")
            if answer_zh
            else None
        )
        cost_estimate = calculate_cost(
            run.provider, run.model_name, tokens_in, tokens_out, route=resolution.route
        )
        llm_answer = LLMAnswer(
            run_id=run_id,
            prompt_id=prompt_id,
            provider=run.provider,
            model_name=run.model_name,
            route=resolution.route,
            raw_answer_zh=answer_zh or "",
            raw_answer_en=answer_en,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency=latency,
            cost_estimate=cost_estimate,
        )
        db.add(llm_answer)
        flush_with_retry(db)
        commit_with_retry(db)
        return _answer_result(run_id, prompt_id, llm_answer.id, True, False)
    except IntegrityError:
        db.rollback()
        existing = _existing_answer(db, run_id, prompt_id)
        if existing:
            return _answer_result(run_id, prompt_id, existing.id, True, True)
        return _answer_result(
            run_id, prompt_id, None, False, False, "IntegrityError on llm_answer insert"
        )
    except Exception as exc:
        logger.error(
            "ensure_llm_answer failed for run=%s prompt=%s: %s",
            run_id,
            prompt_id,
            exc,
            exc_info=True,
        )
        return _answer_result(run_id, prompt_id, None, False, False, str(exc))


def _llm_fetch_concurrency(route: LLMRoute) -> int:
    if not settings.parallel_llm_enabled:
        return 1
    if route == LLMRoute.LOCAL:
        return max(1, settings.local_llm_concurrency)
    return max(1, settings.remote_llm_concurrency)


def _prompt_work_items(
    db: Session,
    run: Run,
    prompts: list[Prompt],
    translator: TranslaterService,
) -> tuple[list[PromptWorkItem], list[LLMRequest]]:
    items: list[PromptWorkItem] = []
    requests: list[LLMRequest] = []
    for prompt in prompts:
        prompt_text_zh = _prompt_text_zh(prompt, translator)
        if not prompt_text_zh:
            logger.warning("Prompt %s has no text, skipping", prompt.id)
            continue
        existing = _existing_answer(db, run.id, prompt.id)
        reusable = (
            None
            if existing
            else find_reusable_answer(
                db, run, prompt_text_zh=prompt_text_zh, prompt_text_en=prompt.text_en
            )
        )
        items.append(
            PromptWorkItem(prompt, prompt_text_zh, prompt.text_en, existing, reusable)
        )
        if not existing and not reusable:
            requests.append(LLMRequest(prompt.id, prompt_text_zh))
    return items, requests


def _raise_on_llm_errors(results: list[LLMResult]) -> None:
    errors = [r.prompt_id for r in results if r.error]
    if errors:
        raise RuntimeError(f"LLM query failed for prompt_ids={errors}")


def fetch_answers_for_run(
    db: Session,
    run: Run,
    prompts: list[Prompt],
    provider: str,
    model_name: str,
) -> list[PreparedAnswer]:
    translator = TranslaterService()
    llm_router = LLMRouter(db)
    resolution = llm_router.resolve(provider, model_name)
    work_items, llm_requests = _prompt_work_items(db, run, prompts, translator)
    concurrency = _llm_fetch_concurrency(resolution.route)

    logger.info(
        "LLM parallel fetch: enabled=%s, concurrency=%s, prompts=%s",
        settings.parallel_llm_enabled,
        concurrency,
        len(llm_requests),
    )

    async def _query_fn(prompt_zh: str):
        return await llm_router.query_with_resolution(resolution, prompt_zh)

    llm_results_by_prompt_id: dict[int, LLMResult] = {}
    if llm_requests:
        if concurrency > 1 and len(llm_requests) > 1:
            llm_results = _run_async(
                fetch_llm_answers_parallel(llm_requests, _query_fn, concurrency)
            )
            _raise_on_llm_errors(llm_results)
            llm_results_by_prompt_id = {r.prompt_id: r for r in llm_results}
        else:
            for req in llm_requests:
                answer_zh, tokens_in, tokens_out, latency = _run_async(
                    _query_fn(req.prompt_text_zh)
                )
                llm_results_by_prompt_id[req.prompt_id] = LLMResult(
                    prompt_id=req.prompt_id,
                    answer_zh=answer_zh,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency=latency,
                )

    prepared_answers: list[PreparedAnswer] = []
    for item in work_items:
        prompt = item.prompt
        logger.info("Processing prompt %s", prompt.id)

        llm_answer = item.existing_answer
        answer_zh = ""
        answer_en = None
        tokens_in = 0
        tokens_out = 0
        latency = 0.0
        cost_estimate = 0.0

        if llm_answer:
            answer_zh = llm_answer.raw_answer_zh
        elif item.reusable_answer:
            reusable = item.reusable_answer
            answer_zh = reusable.raw_answer_zh
            answer_en = reusable.raw_answer_en
            tokens_in = reusable.tokens_in or 0
            tokens_out = reusable.tokens_out or 0
            latency = reusable.latency or 0.0
            cost_estimate = reusable.cost_estimate or 0.0
        else:
            result = llm_results_by_prompt_id.get(prompt.id)
            if not result:
                raise RuntimeError(f"Missing LLM result for prompt {prompt.id}")
            answer_zh = result.answer_zh
            tokens_in = result.tokens_in
            tokens_out = result.tokens_out
            latency = result.latency
            cost_estimate = calculate_cost(
                provider, model_name, tokens_in, tokens_out, route=resolution.route
            )

        if not llm_answer:
            answer_route = resolution.route
            if item.reusable_answer and item.reusable_answer.route:
                answer_route = item.reusable_answer.route
            if answer_zh and not answer_en and not item.reusable_answer:
                answer_en = translator.translate_text_sync(
                    answer_zh, "Chinese", "English"
                )
            llm_answer = LLMAnswer(
                run_id=run.id,
                prompt_id=prompt.id,
                provider=provider,
                model_name=model_name,
                route=answer_route,
                raw_answer_zh=answer_zh,
                raw_answer_en=answer_en,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency=latency,
                cost_estimate=cost_estimate,
            )
            db.add(llm_answer)
            flush_with_retry(db)

        prepared_answers.append(PreparedAnswer(item=item, llm_answer=llm_answer, answer_zh=answer_zh))

    return prepared_answers
