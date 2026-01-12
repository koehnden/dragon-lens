import json

import pytest


def _create_vertical(db_session, name: str, description: str = ""):
    from models import Vertical

    vertical = Vertical(name=name, description=description)
    db_session.add(vertical)
    db_session.flush()
    return vertical


def _create_run(db_session, vertical_id: int):
    from models import Run, RunStatus

    run = Run(vertical_id=vertical_id, provider="qwen", model_name="qwen", status=RunStatus.COMPLETED)
    db_session.add(run)
    db_session.flush()
    return run


def _create_prompt(db_session, vertical_id: int, run_id: int):
    from models import Prompt, PromptLanguage

    prompt = Prompt(vertical_id=vertical_id, run_id=run_id, text_zh="test", language_original=PromptLanguage.ZH)
    db_session.add(prompt)
    db_session.flush()
    return prompt


def _create_answer(db_session, run_id: int, prompt_id: int):
    from models import LLMAnswer

    answer = LLMAnswer(run_id=run_id, prompt_id=prompt_id, provider="qwen", model_name="qwen", raw_answer_zh="x", raw_answer_en=None)
    db_session.add(answer)
    db_session.flush()
    return answer


def _create_brand_and_mention(db_session, vertical_id: int, answer_id: int, name: str):
    from models import Brand, BrandMention

    brand = Brand(vertical_id=vertical_id, display_name=name, original_name=name, translated_name=None, aliases={"zh": [], "en": []}, is_user_input=True)
    db_session.add(brand)
    db_session.flush()
    db_session.add(BrandMention(llm_answer_id=answer_id, brand_id=brand.id, mentioned=True))


def _create_product_and_mention(db_session, vertical_id: int, answer_id: int, name: str):
    from models import Product, ProductMention

    product = Product(vertical_id=vertical_id, brand_id=None, display_name=name, original_name=name, translated_name=None, is_user_input=False)
    db_session.add(product)
    db_session.flush()
    db_session.add(ProductMention(llm_answer_id=answer_id, product_id=product.id, mentioned=True, rank=1))


def _seed_knowledge_vertical(name: str) -> int:
    from models.knowledge_domain import KnowledgeVertical
    from services.knowledge_session import knowledge_session

    with knowledge_session(write=True) as knowledge_db:
        vertical = KnowledgeVertical(name=name)
        knowledge_db.add(vertical)
        knowledge_db.flush()
        return int(vertical.id)


def _knowledge_alias_vertical_id(alias: str) -> int | None:
    from models.knowledge_domain import KnowledgeVerticalAlias
    from services.knowledge_session import knowledge_session
    from services.knowledge_verticals import normalize_entity_key

    with knowledge_session() as knowledge_db:
        key = normalize_entity_key(alias)
        row = knowledge_db.query(KnowledgeVerticalAlias).filter(KnowledgeVerticalAlias.alias_key == key).first()
        return int(row.vertical_id) if row else None


@pytest.mark.asyncio
async def test_auto_match_reuses_existing_canonical(db_session, monkeypatch: pytest.MonkeyPatch):
    cars_id = _seed_knowledge_vertical("Cars")

    vertical = _create_vertical(db_session, "SUV Cars", "SUV segment")
    run = _create_run(db_session, vertical.id)
    prompt = _create_prompt(db_session, vertical.id, run.id)
    answer = _create_answer(db_session, run.id, prompt.id)
    _create_brand_and_mention(db_session, vertical.id, answer.id, "丰田")
    _create_product_and_mention(db_session, vertical.id, answer.id, "RAV4")
    db_session.commit()

    async def _fake_call(*args, **kwargs):
        return json.dumps({
            "match": True,
            "matched_canonical_vertical_name": "Cars",
            "confidence": 0.95,
            "reasons": ["SUV is a car category"],
            "suggested_canonical_vertical_name": "Cars",
            "suggested_description": "Cars and car categories",
        }, ensure_ascii=False)

    monkeypatch.setattr("services.ollama.OllamaService._call_ollama", _fake_call)

    from services.vertical_auto_match import ensure_vertical_grouping_for_run

    canonical_id = await ensure_vertical_grouping_for_run(db_session, run.id)
    assert canonical_id == cars_id
    assert _knowledge_alias_vertical_id("SUV Cars") == cars_id


@pytest.mark.asyncio
async def test_auto_match_creates_new_canonical_when_no_match(db_session, monkeypatch: pytest.MonkeyPatch):
    vertical = _create_vertical(db_session, "Electric SUVs", "EV SUVs")
    run = _create_run(db_session, vertical.id)
    prompt = _create_prompt(db_session, vertical.id, run.id)
    answer = _create_answer(db_session, run.id, prompt.id)
    _create_brand_and_mention(db_session, vertical.id, answer.id, "蔚来")
    _create_product_and_mention(db_session, vertical.id, answer.id, "ES6")
    db_session.commit()

    async def _fake_call(*args, **kwargs):
        return json.dumps({
            "match": False,
            "matched_canonical_vertical_name": None,
            "confidence": 0.0,
            "reasons": ["no suitable canonical vertical"],
            "suggested_canonical_vertical_name": "Cars",
            "suggested_description": "Cars and SUVs",
        }, ensure_ascii=False)

    monkeypatch.setattr("services.ollama.OllamaService._call_ollama", _fake_call)

    from services.vertical_auto_match import ensure_vertical_grouping_for_run

    canonical_id = await ensure_vertical_grouping_for_run(db_session, run.id)
    assert canonical_id is not None
    assert _knowledge_alias_vertical_id("Electric SUVs") == canonical_id

