"""Unit tests for the clustering helpers.

The previous version of this file called the full extraction pipeline with
embedding flags enabled, which made the unit suite depend on live model access.
These tests stay on the actual clustering surface and remain deterministic.
"""

import pytest

from services.brand_recognition.clustering import (
    _cluster_with_embeddings,
    _simple_clustering,
    _split_clusters_by_type,
)
from services.brand_recognition.models import EntityCandidate


@pytest.mark.asyncio
async def test_cluster_with_embeddings_groups_identical_names():
    candidates = [
        EntityCandidate(name="iPhone 14 Pro", source="regex", entity_type="product"),
        EntityCandidate(name="iPhone 14 Pro", source="list", entity_type="product"),
        EntityCandidate(name="Samsung S24", source="regex", entity_type="product"),
    ]

    clusters = await _cluster_with_embeddings(candidates)

    assert set(clusters) == {"iPhone 14 Pro", "Samsung S24"}
    assert len(clusters["iPhone 14 Pro"]) == 2
    assert len(clusters["Samsung S24"]) == 1


def test_simple_clustering_returns_variants_by_canonical_name():
    candidates = {
        "Nike Air Max": [EntityCandidate(name="Nike Air Max", source="regex", entity_type="product")],
        "Adidas Ultraboost": [EntityCandidate(name="Adidas Ultraboost", source="regex", entity_type="product")],
    }

    final_clusters = _simple_clustering(candidates, "Nike", {"zh": [], "en": []})

    assert final_clusters == {
        "Nike Air Max": ["Nike Air Max"],
        "Adidas Ultraboost": ["Adidas Ultraboost"],
    }


def test_split_clusters_by_type_partitions_brands_and_products():
    final_clusters = {
        "Nike": ["Nike"],
        "Air Max 90": ["Air Max 90"],
    }
    filtered_candidates = [
        EntityCandidate(name="Nike", source="regex", entity_type="brand"),
        EntityCandidate(name="Air Max 90", source="regex", entity_type="product"),
    ]

    brands, products = _split_clusters_by_type(final_clusters, filtered_candidates)

    assert brands == {"Nike": ["Nike"]}
    assert products == {"Air Max 90": ["Air Max 90"]}


def test_split_clusters_defaults_unknown_variants_to_brands():
    final_clusters = {"Unknown Canonical": ["Unknown Variant"]}

    brands, products = _split_clusters_by_type(final_clusters, [])

    assert brands == {"Unknown Canonical": ["Unknown Variant"]}
    assert products == {}
