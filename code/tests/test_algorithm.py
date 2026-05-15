"""Tests for the GraphSelect algorithm integration."""
import pytest
from models.openalex_models import Work
from models.graph_node import GraphNode
from models.ranked_paper import RankedPaper
from services.graph_search_service import GraphSearchService
from services.openalex_service import OpenAlexService


class TestAbstractReconstruction:
    def test_reconstruct_basic(self) -> None:
        inverted_index: dict[str, list[int]] = {
            'Array': [0],
            'programming': [1],
            'provides': [2],
            'tools': [3],
        }
        result: str = OpenAlexService.reconstruct_abstract(inverted_index)
        assert result == 'Array programming provides tools'

    def test_reconstruct_with_repeated_words(self) -> None:
        inverted_index: dict[str, list[int]] = {
            'the': [0, 3],
            'cat': [1],
            'sat': [2],
            'mat': [4],
        }
        result: str = OpenAlexService.reconstruct_abstract(inverted_index)
        assert result == 'the cat sat the mat'

    def test_reconstruct_empty(self) -> None:
        result: str = OpenAlexService.reconstruct_abstract({})
        assert result == ''

    def test_reconstruct_single_word(self) -> None:
        result: str = OpenAlexService.reconstruct_abstract({'hello': [0]})
        assert result == 'hello'


class TestExtractOpenAlexId:
    def test_extract_valid_id(self) -> None:
        work = Work(id='https://openalex.org/W2741809807')
        result: str | None = OpenAlexService.extract_openalex_id(work)
        assert result == 'W2741809807'

    def test_extract_none_id(self) -> None:
        work = Work()
        result: str | None = OpenAlexService.extract_openalex_id(work)
        assert result is None

    def test_extract_plain_id(self) -> None:
        work = Work(id='W12345')
        result: str | None = OpenAlexService.extract_openalex_id(work)
        assert result == 'W12345'


class TestExtractDoi:
    def test_extract_full_url_doi(self) -> None:
        work = Work(doi='https://doi.org/10.1038/s41586-020-2649-2')
        result: str | None = OpenAlexService.extract_doi(work)
        assert result == '10.1038/s41586-020-2649-2'

    def test_extract_plain_doi(self) -> None:
        work = Work(doi='10.1038/test')
        result: str | None = OpenAlexService.extract_doi(work)
        assert result == '10.1038/test'

    def test_extract_none_doi(self) -> None:
        work = Work()
        result: str | None = OpenAlexService.extract_doi(work)
        assert result is None


class TestRankedResultGeneration:
    def test_generate_ranked_results_sorting(self) -> None:
        """Results should be sorted by combined score descending."""
        service = GraphSearchService(
            research_questions=['test'],
            seed_doi='10.1234/test',
            api_key='fake-key',
            similarity_weight=0.7,
            pagerank_weight=0.3,
        )

        # Inject graph with different scores
        service._graph = {
            'W1': GraphNode(
                work=Work(id='https://openalex.org/W1', title='Low score'),
                abstract_text='Test',
                embedding=[0.1],
                question_scores={'Q1': 0.2},
                citations=set(),
                references=set(),
                discovered_at_depth=0,
            ),
            'W2': GraphNode(
                work=Work(id='https://openalex.org/W2', title='High score'),
                abstract_text='Test',
                embedding=[0.1],
                question_scores={'Q1': 0.9},
                citations=set(),
                references=set(),
                discovered_at_depth=0,
            ),
            'W3': GraphNode(
                work=Work(id='https://openalex.org/W3', title='Medium score'),
                abstract_text='Test',
                embedding=[0.1],
                question_scores={'Q1': 0.5},
                citations=set(),
                references=set(),
                discovered_at_depth=1,
            ),
        }

        pagerank_scores: dict[str, float] = {'W1': 0.33, 'W2': 0.33, 'W3': 0.33}
        results: list[RankedPaper] = service._generate_ranked_results(pagerank_scores)

        assert len(results) == 3
        assert results[0].work.title == 'High score'
        assert results[-1].work.title == 'Low score'
        # Check combined score formula: 0.7 * max_sim + 0.3 * normalized_pr
        for r in results:
            assert r.combined_score > 0

    def test_is_relevant_above_threshold(self) -> None:
        service = GraphSearchService(
            research_questions=['test'],
            seed_doi='test',
            api_key='key',
            similarity_threshold=0.3,
        )
        scores: dict[str, float] = {'Q1': 0.1, 'Q2': 0.35}
        assert service._is_relevant(scores) is True

    def test_is_relevant_below_threshold(self) -> None:
        service = GraphSearchService(
            research_questions=['test'],
            seed_doi='test',
            api_key='key',
            similarity_threshold=0.3,
        )
        scores: dict[str, float] = {'Q1': 0.1, 'Q2': 0.2}
        assert service._is_relevant(scores) is False

    def test_is_relevant_empty_scores(self) -> None:
        service = GraphSearchService(
            research_questions=['test'],
            seed_doi='test',
            api_key='key',
        )
        assert service._is_relevant({}) is False

    def test_extract_reference_ids(self) -> None:
        service = GraphSearchService(
            research_questions=['test'],
            seed_doi='test',
            api_key='key',
        )
        work = Work(
            referenced_works=[
                'https://openalex.org/W123',
                'https://openalex.org/W456',
                'invalid-url',
            ]
        )
        ids: list[str] = service._extract_reference_ids(work)
        assert ids == ['W123', 'W456']
