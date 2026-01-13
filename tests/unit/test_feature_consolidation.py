from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


@dataclass
class FeatureCluster:
    canonical: str
    members: list[str]


class TestFeatureConsolidation:

    def test_embed_features_returns_array(self):
        from services.feature_consolidation import embed_features

        with patch("services.feature_consolidation.get_embedding_model") as mock_get_model:
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([[0.1, 0.2], [0.3, 0.4]])
            mock_get_model.return_value = mock_model

            features = ["油耗", "空间"]
            embeddings = embed_features(features)

            assert embeddings.shape == (2, 2)
            mock_model.encode.assert_called_once()

    def test_embed_features_empty_list(self):
        from services.feature_consolidation import embed_features

        with patch("services.feature_consolidation.get_embedding_model") as mock_get_model:
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([])
            mock_get_model.return_value = mock_model

            features = []
            embeddings = embed_features(features)

            assert len(embeddings) == 0

    def test_compute_similarity_matrix(self):
        from services.feature_consolidation import compute_similarity_matrix

        embeddings = np.array([
            [1.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
        ])

        sim_matrix = compute_similarity_matrix(embeddings)

        assert sim_matrix.shape == (3, 3)
        assert pytest.approx(sim_matrix[0, 1], 0.01) == 1.0
        assert pytest.approx(sim_matrix[0, 2], 0.01) == 0.0

    def test_find_feature_clusters_identical_features(self):
        from services.feature_consolidation import find_feature_clusters

        features = ["油耗", "油耗"]
        embeddings = np.array([
            [1.0, 0.0],
            [1.0, 0.0],
        ])

        clusters = find_feature_clusters(embeddings, features, threshold=0.85)

        assert len(clusters) == 1
        assert len(clusters[0].members) == 2

    def test_find_feature_clusters_distinct_features(self):
        from services.feature_consolidation import find_feature_clusters

        features = ["油耗", "安全"]
        embeddings = np.array([
            [1.0, 0.0],
            [0.0, 1.0],
        ])

        clusters = find_feature_clusters(embeddings, features, threshold=0.85)

        assert len(clusters) == 2

    def test_find_feature_clusters_with_semantic_similarity(self):
        from services.feature_consolidation import find_feature_clusters

        features = ["油耗", "燃油经济性", "空间"]
        embeddings = np.array([
            [0.9, 0.1, 0.0],
            [0.85, 0.15, 0.0],
            [0.0, 0.0, 1.0],
        ])

        clusters = find_feature_clusters(embeddings, features, threshold=0.85)

        assert len(clusters) == 2
        fuel_cluster = next((c for c in clusters if "油耗" in c.members), None)
        assert fuel_cluster is not None
        assert "燃油经济性" in fuel_cluster.members

    def test_select_canonical_name_most_frequent(self):
        from services.feature_consolidation import select_canonical_name

        members = ["油耗", "燃油经济性", "油耗"]
        frequencies = {"油耗": 10, "燃油经济性": 3}

        canonical = select_canonical_name(members, frequencies)

        assert canonical == "油耗"

    def test_select_canonical_name_shortest_on_tie(self):
        from services.feature_consolidation import select_canonical_name

        members = ["安全", "安全性"]
        frequencies = {"安全": 5, "安全性": 5}

        canonical = select_canonical_name(members, frequencies)

        assert canonical == "安全"

    def test_normalize_feature_name(self):
        from services.feature_consolidation import normalize_feature_name

        assert normalize_feature_name("  油耗  ") == "油耗"
        assert normalize_feature_name("FUEL") == "fuel"
        assert normalize_feature_name("油 耗") == "油 耗"


class TestFeatureConsolidationService:

    def test_consolidate_features_empty_list(self):
        from services.feature_consolidation import consolidate_feature_list

        with patch("services.feature_consolidation.get_embedding_model") as mock_get_model:
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([])
            mock_get_model.return_value = mock_model

            result = consolidate_feature_list([], threshold=0.85)

            assert result.clusters == []

    def test_consolidate_features_single_feature(self):
        from services.feature_consolidation import consolidate_feature_list

        with patch("services.feature_consolidation.get_embedding_model") as mock_get_model:
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([[0.5, 0.5]])
            mock_get_model.return_value = mock_model

            result = consolidate_feature_list(["油耗"], threshold=0.85)

            assert len(result.clusters) == 1
            assert result.clusters[0].canonical == "油耗"

    def test_consolidate_features_creates_mapping(self):
        from services.feature_consolidation import consolidate_feature_list

        with patch("services.feature_consolidation.get_embedding_model") as mock_get_model:
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([
                [0.9, 0.1],
                [0.88, 0.12],
                [0.1, 0.9],
            ])
            mock_get_model.return_value = mock_model

            features = ["油耗", "燃油经济性", "空间"]
            result = consolidate_feature_list(features, threshold=0.85)

            assert "燃油经济性" in result.alias_to_canonical


class TestThresholdSensitivity:

    def test_high_threshold_fewer_clusters(self):
        from services.feature_consolidation import find_feature_clusters

        features = ["油耗", "燃油", "空间"]
        embeddings = np.array([
            [0.9, 0.1],
            [0.8, 0.2],
            [0.1, 0.9],
        ])

        clusters_low = find_feature_clusters(embeddings, features, threshold=0.7)
        clusters_high = find_feature_clusters(embeddings, features, threshold=0.95)

        assert len(clusters_low) <= len(clusters_high)

    def test_default_threshold_reasonable(self):
        from services.feature_consolidation import DEFAULT_THRESHOLD

        assert 0.7 <= DEFAULT_THRESHOLD <= 0.95


class TestFeatureConsolidationIntegration:

    @pytest.mark.skip(reason="Requires real model; run manually")
    def test_real_model_semantic_similarity(self):
        from services.feature_consolidation import consolidate_feature_list

        features = ["油耗", "燃油经济性", "mpg", "空间", "车内空间", "安全"]
        result = consolidate_feature_list(features, threshold=0.85)

        fuel_cluster = next(
            (c for c in result.clusters if "油耗" in c.canonical or "燃油" in c.canonical),
            None
        )
        assert fuel_cluster is not None
        assert len(fuel_cluster.members) >= 2
