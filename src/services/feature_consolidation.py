import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 0.85
MODEL_NAME = "BAAI/bge-small-zh-v1.5"

_embedding_model = None


def get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        import torch
        from sentence_transformers import SentenceTransformer
        logger.info(f"Loading embedding model: {MODEL_NAME}")
        device = "cpu"
        _embedding_model = SentenceTransformer(MODEL_NAME, device=device)
    return _embedding_model


@dataclass
class FeatureCluster:
    canonical: str
    members: list[str] = field(default_factory=list)


@dataclass
class ConsolidationResult:
    clusters: list[FeatureCluster] = field(default_factory=list)
    alias_to_canonical: dict[str, str] = field(default_factory=dict)


def normalize_feature_name(name: str) -> str:
    return name.strip().lower() if name else ""


def embed_features(features: list[str]) -> np.ndarray:
    if not features:
        return np.array([])
    model = get_embedding_model()
    return model.encode(features, convert_to_numpy=True)


def compute_similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    if len(embeddings) == 0:
        return np.array([])

    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1, norms)
    normalized = embeddings / norms

    return np.dot(normalized, normalized.T)


def find_feature_clusters(
    embeddings: np.ndarray,
    features: list[str],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[FeatureCluster]:
    if len(features) == 0:
        return []

    sim_matrix = compute_similarity_matrix(embeddings)
    n = len(features)
    visited = [False] * n
    clusters = []

    for i in range(n):
        if visited[i]:
            continue

        cluster_members = [features[i]]
        visited[i] = True

        for j in range(i + 1, n):
            if not visited[j] and sim_matrix[i, j] >= threshold:
                cluster_members.append(features[j])
                visited[j] = True

        clusters.append(FeatureCluster(
            canonical=cluster_members[0],
            members=cluster_members,
        ))

    return clusters


def select_canonical_name(
    members: list[str],
    frequencies: Optional[dict[str, int]] = None,
) -> str:
    if not members:
        return ""
    if len(members) == 1:
        return members[0]

    frequencies = frequencies or {}

    def sort_key(name):
        freq = frequencies.get(name, 0)
        return (-freq, len(name), name)

    sorted_members = sorted(members, key=sort_key)
    return sorted_members[0]


def consolidate_feature_list(
    features: list[str],
    threshold: float = DEFAULT_THRESHOLD,
    frequencies: Optional[dict[str, int]] = None,
) -> ConsolidationResult:
    if not features:
        return ConsolidationResult()

    unique_features = list(set(features))
    embeddings = embed_features(unique_features)
    clusters = find_feature_clusters(embeddings, unique_features, threshold)

    frequencies = frequencies or {}
    result = ConsolidationResult()

    for cluster in clusters:
        canonical = select_canonical_name(cluster.members, frequencies)
        cluster.canonical = canonical
        result.clusters.append(cluster)

        for member in cluster.members:
            if member != canonical:
                result.alias_to_canonical[member] = canonical

    return result
