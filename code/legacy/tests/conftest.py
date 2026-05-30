import pytest
from fastapi.testclient import TestClient
from main import app
from models.openalex_models import Work


@pytest.fixture
def client() -> TestClient:
    """Create a FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def sample_work() -> Work:
    """Create a sample Work for testing."""
    return Work(
        id='https://openalex.org/W2741809807',
        doi='https://doi.org/10.1038/s41586-020-2649-2',
        title='Array programming with NumPy',
        display_name='Array programming with NumPy',
        abstract_inverted_index={
            'Array': [0],
            'programming': [1],
            'provides': [2],
            'powerful': [3],
            'tools': [4],
            'for': [5],
            'scientific': [6],
            'computing': [7],
        },
        cited_by_count=5000,
        publication_year=2020,
        referenced_works=[
            'https://openalex.org/W123456789',
            'https://openalex.org/W987654321',
        ],
    )


@pytest.fixture
def sample_work_no_abstract() -> Work:
    """Create a sample Work without abstract."""
    return Work(
        id='https://openalex.org/W1234567890',
        doi='https://doi.org/10.1234/test',
        title='Test Paper Without Abstract',
        cited_by_count=10,
    )


@pytest.fixture
def sample_embedding_a() -> list[float]:
    """Sample embedding vector A."""
    return [1.0, 2.0, 3.0, 4.0, 5.0]


@pytest.fixture
def sample_embedding_b() -> list[float]:
    """Sample embedding vector B (similar to A)."""
    return [1.1, 2.1, 3.1, 4.1, 5.1]


@pytest.fixture
def sample_embedding_c() -> list[float]:
    """Sample embedding vector C (orthogonal/dissimilar to A)."""
    return [-5.0, 4.0, -3.0, 2.0, -1.0]
