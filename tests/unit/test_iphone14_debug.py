from services.brand_recognition import (
    generate_candidates,
    _filter_candidates_simple,
    _simple_clustering,
    _build_alias_lookup,
    _default_alias_table,
    normalize_text_for_ner
)


def test_iphone14_full_pipeline():
    text = "1. iPhone14 Pro - great phone"
    normalized_text = normalize_text_for_ner(text)
    print(f"Normalized text: {normalized_text}")

    candidates = generate_candidates(normalized_text, "iPhone", {"zh": ["苹果"], "en": ["iPhone"]})
    print(f"Generated {len(candidates)} candidates:")
    for c in candidates:
        print(f"  - {c.name} (source: {c.source})")

    filtered = _filter_candidates_simple(candidates)
    print(f"\nFiltered to {len(filtered)} candidates:")
    for c in filtered:
        print(f"  - {c.name} (source: {c.source})")

    embedding_clusters = {c.name: [c] for c in filtered}
    print(f"\nEmbedding clusters: {list(embedding_clusters.keys())}")

    normalized_aliases = _build_alias_lookup("iPhone", {"zh": ["苹果"], "en": ["iPhone"]}, _default_alias_table())
    print(f"\nNormalized aliases: {normalized_aliases}")

    final = _simple_clustering(embedding_clusters, "iPhone", {"zh": ["苹果"], "en": ["iPhone"]})
    print(f"\nFinal clusters:")
    for canonical, members in final.items():
        print(f"  {canonical}: {members}")

    assert any("14" in name for name in final.keys()), f"Expected iPhone14 in final output: {final.keys()}"
