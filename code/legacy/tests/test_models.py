"""Tests for Pydantic models."""
import pytest
from pydantic import ValidationError

from models.openalex_models import Work, WorksResponse, WorksMeta, Authorship, Author
from models.graph_node import GraphNode
from models.ranked_paper import RankedPaper
from models.progress import GraphSearchProgress, GraphSearchStatus


class TestWorkModel:
    def test_work_with_all_fields(self, sample_work: Work) -> None:
        assert sample_work.id == 'https://openalex.org/W2741809807'
        assert sample_work.doi == 'https://doi.org/10.1038/s41586-020-2649-2'
        assert sample_work.title == 'Array programming with NumPy'
        assert sample_work.cited_by_count == 5000
        assert len(sample_work.referenced_works) == 2

    def test_work_with_minimal_fields(self) -> None:
        work = Work()
        assert work.id is None
        assert work.doi is None
        assert work.title is None
        assert work.cited_by_count == 0
        assert work.referenced_works == []

    def test_work_with_abstract_inverted_index(self, sample_work: Work) -> None:
        assert sample_work.abstract_inverted_index is not None
        assert 'Array' in sample_work.abstract_inverted_index
        assert sample_work.abstract_inverted_index['Array'] == [0]

    def test_works_response(self) -> None:
        response = WorksResponse(
            meta=WorksMeta(count=10, page=1, per_page=25),
            results=[Work(title='Test')],
        )
        assert response.meta is not None
        assert response.meta.count == 10
        assert len(response.results) == 1

    def test_authorship(self) -> None:
        authorship = Authorship(
            author=Author(display_name='John Doe', orcid='0000-0001-2345-6789'),
            author_position='first',
        )
        assert authorship.author.display_name == 'John Doe'


class TestGraphNodeModel:
    def test_graph_node_creation(self, sample_work: Work) -> None:
        node = GraphNode(
            work=sample_work,
            abstract_text='Array programming provides powerful tools',
            embedding=[0.1, 0.2, 0.3],
            question_scores={'Q1': 0.8, 'Q2': 0.5},
            citations={'W111', 'W222'},
            references={'W333'},
            discovered_at_depth=0,
        )
        assert node.max_score == 0.8
        assert node.openalex_id == 'W2741809807'
        assert node.clean_doi == '10.1038/s41586-020-2649-2'

    def test_graph_node_empty_scores(self, sample_work: Work) -> None:
        node = GraphNode(
            work=sample_work,
            abstract_text='',
            embedding=[],
            question_scores={},
            citations=set(),
            references=set(),
            discovered_at_depth=0,
        )
        assert node.max_score == 0.0

    def test_graph_node_no_doi(self) -> None:
        work = Work(id='https://openalex.org/W999')
        node = GraphNode(
            work=work,
            abstract_text='',
            embedding=[],
            question_scores={},
            citations=set(),
            references=set(),
            discovered_at_depth=1,
        )
        assert node.clean_doi is None
        assert node.openalex_id == 'W999'


class TestRankedPaperModel:
    def test_ranked_paper(self, sample_work: Work) -> None:
        paper = RankedPaper(
            work=sample_work,
            abstract_text='Test abstract',
            max_similarity_score=0.85,
            pagerank_score=0.6,
            combined_score=0.775,
            depth=1,
            question_scores={'Q1': 0.85},
        )
        assert paper.combined_score == 0.775
        assert paper.depth == 1


class TestProgressModel:
    def test_progress_status_enum(self) -> None:
        assert GraphSearchStatus.IDLE == 'idle'
        assert GraphSearchStatus.COMPLETED == 'completed'

    def test_progress_creation(self) -> None:
        progress = GraphSearchProgress(
            status=GraphSearchStatus.EXPLORING_LEVEL,
            current_depth=2,
            max_depth=3,
            papers_processed=15,
            relevant_papers_found=5,
            message='Processing...',
        )
        assert progress.current_depth == 2
        assert progress.relevant_papers_found == 5
