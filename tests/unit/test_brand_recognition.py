import asyncio

from services import brand_recognition
from services.brand_recognition import (
    EntityCandidate,
    canonicalize_entities,
    extract_entities,
    generate_candidates,
)


def test_generate_candidates_uses_heuristics_and_seed():
    text = "大众ID.4对比特斯拉Model Y，宋PLUS DM-i也很热门。"
    aliases = {"zh": ["大众汽车"], "en": ["Volkswagen", "VW"]}
    candidates = generate_candidates(text, "大众", aliases)
    names = {candidate.name for candidate in candidates}
    assert "大众" in names
    assert "Model Y" in names or "ModelY" in names
    assert "ID.4" in names
    assert "宋PLUS" in {n.replace(" ", "") for n in names}


def test_canonicalize_entities_maps_aliases_and_products():
    candidates = [
        EntityCandidate(name="VW", source="seed"),
        EntityCandidate(name="Volkswagen", source="quoted"),
        EntityCandidate(name="大眾", source="regex"),
        EntityCandidate(name="宋Plus DM-i", source="regex"),
    ]
    aliases = {"zh": [], "en": ["VW"]}
    canonical = canonicalize_entities(candidates, "大众", aliases)
    assert "大众" in canonical
    assert canonical["大众"] == sorted(["VW", "Volkswagen", "大眾"])
    assert any(key.startswith("宋plus".lower()) for key in canonical)


def test_extract_entities_unifies_primary_and_competitors():
    text = "我喜欢大众ID.4，也会考虑特斯拉Model Y。"
    aliases = {"zh": ["上汽大众"], "en": ["VW"]}
    canonical = extract_entities(text, "大众", aliases)
    assert "大众" in canonical
    tesla_key = next(key for key in canonical if "特斯拉" in key or "tesla" in key)
    assert "特斯拉" in canonical[tesla_key] or "Tesla" in canonical[tesla_key]


def test_cluster_with_embeddings_falls_back_on_error(monkeypatch):
    async def error_embeddings(*args, **kwargs):
        raise RuntimeError("Embedding model unavailable")

    monkeypatch.setattr("services.brand_recognition._get_embeddings_ollama", error_embeddings)

    candidates = [
        EntityCandidate(name="Alpha", source="seed"),
        EntityCandidate(name="Beta", source="regex"),
    ]

    clusters = asyncio.run(brand_recognition._cluster_with_embeddings(candidates))

    assert clusters == {candidate.name: [candidate] for candidate in candidates}
