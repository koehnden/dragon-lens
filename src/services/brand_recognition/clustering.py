"""
Entity clustering and canonicalization.

This module contains functions for clustering similar entities together
using embedding-based clustering and LLM-assisted clustering.
"""

import logging
from typing import Dict, List

from services.brand_recognition.models import EntityCandidate

logger = logging.getLogger(__name__)


async def _cluster_with_embeddings(candidates: List[EntityCandidate]) -> Dict[str, List[EntityCandidate]]:
    """Cluster candidates using embedding similarity."""
    # Simplified version - in real implementation this would use embeddings
    # For now, just group by name
    clusters: Dict[str, List[EntityCandidate]] = {}
    for candidate in candidates:
        if candidate.name not in clusters:
            clusters[candidate.name] = []
        clusters[candidate.name].append(candidate)
    return clusters


async def _llm_assisted_clustering(
    embedding_clusters: Dict[str, List[EntityCandidate]],
    primary_brand: str,
    aliases: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """Refine clusters using LLM assistance."""
    # Simplified version - in real implementation this would use LLM
    # For now, just return the embedding clusters as canonical names
    final_clusters: Dict[str, List[str]] = {}
    for name, candidates in embedding_clusters.items():
        if name:
            final_clusters[name] = [name]
    return final_clusters


def _simple_clustering(
    embedding_clusters: Dict[str, List[EntityCandidate]],
    primary_brand: str,
    aliases: Dict[str, List[str]],
) -> Dict[str, List[str]]:
    """Simple clustering without LLM assistance."""
    final_clusters: Dict[str, List[str]] = {}
    for name, candidates in embedding_clusters.items():
        if name:
            final_clusters[name] = [name]
    return final_clusters


def _split_clusters_by_type(
    final_clusters: Dict[str, List[str]],
    filtered_candidates: List[EntityCandidate],
) -> tuple[Dict[str, List[str]], Dict[str, List[str]]]:
    """Split clusters into brands and products."""
    brands: Dict[str, List[str]] = {}
    products: Dict[str, List[str]] = {}
    
    candidate_map = {c.name: c for c in filtered_candidates}
    
    for canonical, variants in final_clusters.items():
        if not variants:
            continue
            
        # Determine type based on first variant
        first_variant = variants[0]
        candidate = candidate_map.get(first_variant)
        if candidate and candidate.entity_type == "product":
            products[canonical] = variants
        else:
            brands[canonical] = variants
    
    return brands, products


def _filter_by_list_position(candidates: List[EntityCandidate], text: str) -> List[EntityCandidate]:
    """Filter candidates based on their position in list items."""
    # Simplified version - in real implementation this would analyze list positions
    return candidates
