"""Graph node model for the citation graph.

Ported from the Dart ``GraphNode`` class in ``graph_search_service.dart``.
"""

import re

from pydantic import BaseModel, computed_field

from models.openalex_models import Work


class GraphNode(BaseModel):
    """Represents a node in the citation graph.

    Contains paper metadata, embedding vector, relevance scores,
    and connections to other papers (citations and references).
    Ported from Dart GraphNode in graph_search_service.dart.
    """

    work: Work
    abstract_text: str
    embedding: list[float]
    question_scores: dict[str, float]
    citations: set[str]
    references: set[str]
    discovered_at_depth: int

    model_config = {"arbitrary_types_allowed": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def max_score(self) -> float:
        """Return the highest similarity score across all questions."""
        if not self.question_scores:
            return 0.0
        return max(self.question_scores.values())

    @computed_field  # type: ignore[prop-decorator]
    @property
    def openalex_id(self) -> str:
        """Extract the OpenAlex ID (``W…``) from the work URL."""
        if self.work.id:
            match = re.search(r"W\d+", self.work.id)
            if match:
                return match.group(0)
        return ""

    @computed_field  # type: ignore[prop-decorator]
    @property
    def clean_doi(self) -> str | None:
        """Extract a clean DOI without the ``https://doi.org/`` prefix."""
        if self.work.doi:
            if self.work.doi.startswith("https://doi.org/"):
                return self.work.doi[16:]
            return self.work.doi
        return None
