"""Tests for PageRank calculation."""
import pytest
from models.openalex_models import Work
from models.graph_node import GraphNode
from services.graph_search_service import GraphSearchService


def _make_node(
    work_id: str,
    citations: set[str] | None = None,
    references: set[str] | None = None,
    depth: int = 0,
) -> GraphNode:
    """Helper to create a minimal GraphNode for testing."""
    return GraphNode(
        work=Work(id=f'https://openalex.org/{work_id}'),
        abstract_text='Test abstract',
        embedding=[0.1],
        question_scores={'Q1': 0.5},
        citations=citations or set(),
        references=references or set(),
        discovered_at_depth=depth,
    )


class TestPageRank:
    def _create_service_with_graph(self, graph: dict[str, GraphNode]) -> GraphSearchService:
        """Create a GraphSearchService and inject a pre-built graph."""
        service = GraphSearchService(
            research_questions=['test'],
            seed_doi='10.1234/test',
            api_key='fake-key',
        )
        service._graph = graph
        return service

    def test_empty_graph(self) -> None:
        service = self._create_service_with_graph({})
        scores: dict[str, float] = service._calculate_pagerank()
        assert scores == {}

    def test_single_node(self) -> None:
        """Single isolated node converges to (1-d)/n with no incoming links."""
        graph: dict[str, GraphNode] = {
            'W1': _make_node('W1'),
        }
        service = self._create_service_with_graph(graph)
        scores: dict[str, float] = service._calculate_pagerank()
        assert 'W1' in scores
        # Single node with no self-links: score = (1-d)/n = (1-0.85)/1 = 0.15
        assert abs(scores['W1'] - 0.15) < 0.01

    def test_two_nodes_linked(self) -> None:
        """Two nodes citing each other should have equal PageRank."""
        graph: dict[str, GraphNode] = {
            'W1': _make_node('W1', citations={'W2'}),
            'W2': _make_node('W2', citations={'W1'}),
        }
        service = self._create_service_with_graph(graph)
        scores: dict[str, float] = service._calculate_pagerank()
        assert abs(scores['W1'] - scores['W2']) < 0.01

    def test_star_topology(self) -> None:
        """Central node cited by all others should have highest PageRank."""
        graph: dict[str, GraphNode] = {
            'W1': _make_node('W1'),  # Central — cited by W2, W3, W4
            'W2': _make_node('W2', citations={'W1'}),
            'W3': _make_node('W3', citations={'W1'}),
            'W4': _make_node('W4', citations={'W1'}),
        }
        service = self._create_service_with_graph(graph)
        scores: dict[str, float] = service._calculate_pagerank()
        # W1 should have the highest score
        assert scores['W1'] > scores['W2']
        assert scores['W1'] > scores['W3']
        assert scores['W1'] > scores['W4']

    def test_pagerank_sums_close_to_one(self) -> None:
        """PageRank scores should approximately sum to 1."""
        graph: dict[str, GraphNode] = {
            'W1': _make_node('W1', citations={'W2', 'W3'}),
            'W2': _make_node('W2', references={'W1'}),
            'W3': _make_node('W3', citations={'W1'}),
        }
        service = self._create_service_with_graph(graph)
        scores: dict[str, float] = service._calculate_pagerank()
        total: float = sum(scores.values())
        assert abs(total - 1.0) < 0.05

    def test_damping_factor_effect(self) -> None:
        """Higher damping should amplify differences between linked and unlinked nodes."""
        # Use a star topology where W1 is cited by W2, W3, W4
        # so that damping actually affects the score distribution.
        graph: dict[str, GraphNode] = {
            'W1': _make_node('W1'),  # Central — cited by all
            'W2': _make_node('W2', citations={'W1'}),
            'W3': _make_node('W3', citations={'W1'}),
            'W4': _make_node('W4', citations={'W1'}),
        }
        service = self._create_service_with_graph(graph)

        scores_high: dict[str, float] = service._calculate_pagerank(damping_factor=0.85)
        scores_low: dict[str, float] = service._calculate_pagerank(damping_factor=0.15)

        # With high damping, W1 should get a bigger boost from incoming links
        # With low damping, scores are more uniform (closer to 1/n)
        diff_high: float = abs(scores_high['W1'] - scores_high['W2'])
        diff_low: float = abs(scores_low['W1'] - scores_low['W2'])
        assert diff_low < diff_high
