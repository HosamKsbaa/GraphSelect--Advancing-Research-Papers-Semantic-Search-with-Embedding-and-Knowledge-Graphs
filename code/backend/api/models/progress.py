"""Progress and status models for the graph search process."""

from enum import Enum

from pydantic import BaseModel


class GraphSearchStatus(str, Enum):
    """Status of the graph search process."""

    IDLE = "idle"
    EMBEDDING_QUESTIONS = "embedding_questions"
    PROCESSING_SEED = "processing_seed"
    EXPLORING_LEVEL = "exploring_level"
    CALCULATING_PAGERANK = "calculating_pagerank"
    COMPLETED = "completed"
    ERROR = "error"


class GraphSearchProgress(BaseModel):
    """Progress information emitted during a graph search."""

    status: GraphSearchStatus
    current_depth: int = 0
    max_depth: int = 0
    papers_processed: int = 0
    relevant_papers_found: int = 0
    current_level_progress: int = 0
    current_level_total: int = 0
    message: str | None = None
    error_message: str | None = None
