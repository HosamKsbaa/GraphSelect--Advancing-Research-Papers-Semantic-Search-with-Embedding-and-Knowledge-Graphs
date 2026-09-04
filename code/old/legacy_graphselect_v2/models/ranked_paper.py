"""Ranked paper model returned by the GraphSelect search.

Ported from the Dart ``RankedPaper`` class in ``graph_search_service.dart``.
"""

from pydantic import BaseModel

from models.openalex_models import Work


class RankedPaper(BaseModel):
    """Represents a ranked paper result from the GraphSelect search.

    Papers are ranked by a combined score: 70 % cosine similarity + 30 % PageRank.
    Ported from Dart RankedPaper in graph_search_service.dart.
    """

    work: Work
    abstract_text: str
    max_similarity_score: float
    pagerank_score: float
    combined_score: float
    depth: int
    question_scores: dict[str, float]
