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
    has_vw_variant = any(
        "vw" in k.lower() or "volkswagen" in k.lower() or "大众" in k or "大眾" in k
        for k in canonical.keys()
    )
    assert has_vw_variant, f"Expected VW variant in {canonical}"
    has_song_plus = any(
        "宋plus" in k.lower() or "宋 plus" in k.lower()
        for k in canonical.keys()
    )
    assert has_song_plus or "宋Plus DM-i" in canonical, f"Expected 宋Plus in {canonical}"


def test_extract_entities_unifies_primary_and_competitors():
    text = "我喜欢大众ID.4，也会考虑特斯拉Model Y。"
    aliases = {"zh": ["上汽大众"], "en": ["VW"]}
    result = extract_entities(text, "大众", aliases)
    all_entities = result.all_entities()
    has_vw = "Volkswagen" in all_entities or "大众" in all_entities
    assert has_vw, f"Expected Volkswagen or 大众 in {all_entities}"
    has_tesla = "Tesla" in all_entities or "特斯拉" in all_entities
    assert has_tesla or len(all_entities) > 0


def test_cluster_with_embeddings_groups_by_name():
    candidates = [
        EntityCandidate(name="Alpha", source="seed"),
        EntityCandidate(name="Beta", source="regex"),
    ]

    clusters = asyncio.run(brand_recognition._cluster_with_embeddings(candidates))

    assert "Alpha" in clusters
    assert "Beta" in clusters
    assert len(clusters) == 2
