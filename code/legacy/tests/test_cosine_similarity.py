"""Tests for cosine similarity calculation."""
import math
import pytest
from services.graph_search_service import GraphSearchService


class TestCosineSimilarity:
    def test_identical_vectors(self) -> None:
        a: list[float] = [1.0, 2.0, 3.0]
        result: float = GraphSearchService.cosine_similarity(a, a)
        assert abs(result - 1.0) < 1e-10

    def test_orthogonal_vectors(self) -> None:
        a: list[float] = [1.0, 0.0]
        b: list[float] = [0.0, 1.0]
        result: float = GraphSearchService.cosine_similarity(a, b)
        assert abs(result) < 1e-10

    def test_opposite_vectors(self) -> None:
        a: list[float] = [1.0, 2.0, 3.0]
        b: list[float] = [-1.0, -2.0, -3.0]
        result: float = GraphSearchService.cosine_similarity(a, b)
        assert abs(result - (-1.0)) < 1e-10

    def test_similar_vectors(self, sample_embedding_a: list[float], sample_embedding_b: list[float]) -> None:
        result: float = GraphSearchService.cosine_similarity(sample_embedding_a, sample_embedding_b)
        assert result > 0.99  # Very similar vectors

    def test_dissimilar_vectors(self, sample_embedding_a: list[float], sample_embedding_c: list[float]) -> None:
        result: float = GraphSearchService.cosine_similarity(sample_embedding_a, sample_embedding_c)
        assert result < 0.5  # Dissimilar vectors

    def test_empty_vectors(self) -> None:
        result: float = GraphSearchService.cosine_similarity([], [])
        assert result == 0.0

    def test_different_length_vectors(self) -> None:
        a: list[float] = [1.0, 2.0]
        b: list[float] = [1.0, 2.0, 3.0]
        result: float = GraphSearchService.cosine_similarity(a, b)
        assert result == 0.0

    def test_zero_vector(self) -> None:
        a: list[float] = [0.0, 0.0, 0.0]
        b: list[float] = [1.0, 2.0, 3.0]
        result: float = GraphSearchService.cosine_similarity(a, b)
        assert result == 0.0

    def test_unit_vectors(self) -> None:
        a: list[float] = [1.0, 0.0, 0.0]
        b: list[float] = [0.0, 1.0, 0.0]
        result: float = GraphSearchService.cosine_similarity(a, b)
        assert abs(result) < 1e-10

    def test_known_angle(self) -> None:
        """Test vectors at 45 degrees."""
        a: list[float] = [1.0, 0.0]
        b: list[float] = [1.0, 1.0]
        expected: float = 1.0 / math.sqrt(2)
        result: float = GraphSearchService.cosine_similarity(a, b)
        assert abs(result - expected) < 1e-10
