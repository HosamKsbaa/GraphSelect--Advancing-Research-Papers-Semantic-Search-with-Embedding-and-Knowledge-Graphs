"""Citation Hallucination Verification Engine for ALRS v2.

Provides deterministic and database-backed verification of academic citations
in drafted literature reviews, ensuring zero hallucinated DOIs or fabricated
sources.

Functions and Classes:
    - CitationVerificationResult: Structured dataclass of verification metrics
    - CitationVerifier: Verification engine querying Neo4j knowledge graph
    - extract_dois: Extract and normalize DOIs from text
    - normalize_doi: Canonicalize DOI string
    - verify_citation_grounding: Fast in-memory verification against a known set
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService

# Regex pattern for matching DOI expressions
# Matches standard DOIs like 10.1000/182, 10.1145/3308558.3313508, 10.48550/arXiv.1706.03762
DOI_PATTERN = re.compile(r"(?:doi:|(?:https?://)?(?:dx\.)?doi\.org/)?\b(10\.\d{4,9}/[^\s,)}\]>\"']+)", re.IGNORECASE)


def normalize_doi(doi: str) -> str:
    """Normalize a DOI string to canonical lowercase format without prefixes or punctuation.

    Args:
        doi: Raw DOI string (e.g., 'https://doi.org/10.1000/AbC.', 'doi: 10.1000/ABC', '(DOI: 10.1000/XYZ)')

    Returns:
        Canonical lowercase DOI string (e.g., '10.1000/abc')
    """
    if not doi:
        return ""
    doi = doi.strip()
    # Strip leading punctuation/brackets/parentheses
    doi = re.sub(r"^[\(\[\{\"\']+", "", doi).strip()
    # Strip URL prefixes
    doi = re.sub(r"^(?:https?://)?(?:dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    # Strip doi: prefix
    doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    # Strip trailing punctuation often captured at the end of sentences
    doi = re.sub(r"[.,;:\)>\]\}\"']+$", "", doi)
    return doi.strip().lower()


def extract_dois(text: str) -> list[str]:
    """Extract and normalize all unique DOIs found in the given text.

    Args:
        text: Markdown, LaTeX, or plain text containing citations.

    Returns:
        List of unique, normalized lowercase DOIs in order of appearance.
    """
    if not text:
        return []

    found = DOI_PATTERN.findall(text)
    seen: set[str] = set()
    result: list[str] = []

    for raw in found:
        norm = normalize_doi(raw)
        if norm and norm.startswith("10.") and "/" in norm and norm not in seen:
            seen.add(norm)
            result.append(norm)

    return result


@dataclass
class CitationVerificationResult:
    """Structured report of citation verification results."""

    cited_dois: list[str] = field(default_factory=list)
    verified_dois: list[str] = field(default_factory=list)
    hallucinated_dois: list[str] = field(default_factory=list)
    missing_assigned_dois: list[str] = field(default_factory=list)
    total_cited: int = 0
    hallucination_rate: float = 0.0
    coverage_rate: float = 1.0
    is_grounded: bool = True
    passed: bool = True
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert result to a standard serializable dictionary."""
        return {
            "cited_dois": self.cited_dois,
            "verified_dois": self.verified_dois,
            "hallucinated_dois": self.hallucinated_dois,
            "missing_assigned_dois": self.missing_assigned_dois,
            "total_cited": self.total_cited,
            "hallucination_rate": round(self.hallucination_rate, 4),
            "coverage_rate": round(self.coverage_rate, 4),
            "is_grounded": self.is_grounded,
            "passed": self.passed,
            "details": self.details,
        }


def verify_citation_grounding(
    text: str,
    known_dois: set[str] | list[str],
    assigned_dois: list[str] | None = None,
) -> CitationVerificationResult:
    """Synchronously verify citations in text against a set of known valid DOIs.

    Args:
        text: Text to evaluate.
        known_dois: Collection of valid DOIs present in the knowledge graph.
        assigned_dois: Optional list of DOIs that were assigned to be cited.

    Returns:
        CitationVerificationResult containing verified and hallucinated citations.
    """
    normalized_known = {normalize_doi(d) for d in known_dois if d}
    assigned_set = {normalize_doi(d) for d in (assigned_dois or []) if d}
    valid_set = normalized_known | assigned_set

    cited = extract_dois(text)

    verified: list[str] = []
    hallucinated: list[str] = []

    for d in cited:
        if d in valid_set:
            verified.append(d)
        else:
            hallucinated.append(d)

    missing: list[str] = []
    if assigned_dois:
        for a in assigned_dois:
            norm_a = normalize_doi(a)
            if norm_a and norm_a not in cited:
                missing.append(a)

    total = len(cited)
    hallucination_rate = len(hallucinated) / total if total > 0 else 0.0
    assigned_count = len(assigned_dois) if assigned_dois is not None else len(verified)
    coverage_rate = (assigned_count - len(missing)) / assigned_count if assigned_count > 0 else 1.0
    is_grounded = len(hallucinated) == 0
    passed = is_grounded and len(missing) == 0

    return CitationVerificationResult(
        cited_dois=cited,
        verified_dois=verified,
        hallucinated_dois=hallucinated,
        missing_assigned_dois=missing,
        total_cited=total,
        hallucination_rate=hallucination_rate,
        coverage_rate=coverage_rate,
        is_grounded=is_grounded,
        passed=passed,
    )


class CitationVerifier:
    """Async citation verification engine backed by Neo4j graph database."""

    def __init__(self, neo4j: Neo4jService | None = None) -> None:
        self._neo4j = neo4j

    async def verify_text_citations(
        self,
        text: str,
        project_id: str,
        assigned_dois: list[str] | None = None,
    ) -> CitationVerificationResult:
        """Verify citations in text against Neo4j knowledge graph for the given project.

        Args:
            text: Markdown or text draft containing citations.
            project_id: The project UUID.
            assigned_dois: Optional list of assigned DOIs.

        Returns:
            CitationVerificationResult with zero hallucination verification status.
        """
        cited = extract_dois(text)
        if not cited and not assigned_dois:
            return CitationVerificationResult(
                cited_dois=[],
                verified_dois=[],
                hallucinated_dois=[],
                missing_assigned_dois=[],
                total_cited=0,
                hallucination_rate=0.0,
                coverage_rate=1.0,
                is_grounded=True,
                passed=True,
            )

        assigned_set = {normalize_doi(d) for d in (assigned_dois or []) if d}
        verified: list[str] = []
        hallucinated: list[str] = []
        details: dict[str, Any] = {}

        if self._neo4j is not None:
            # Query graph for project papers and specific DOIs
            for doi in cited:
                if doi in assigned_set:
                    verified.append(doi)
                    details[doi] = {"status": "verified_assigned_doi"}
                else:
                    paper = await self._neo4j.get_paper_by_doi(doi)
                    if paper:
                        verified.append(doi)
                        details[doi] = {
                            "title": paper.get("title", "Unknown") if isinstance(paper, dict) else "Verified",
                            "year": paper.get("year") if isinstance(paper, dict) else None,
                            "status": "verified_in_graph",
                        }
                    else:
                        hallucinated.append(doi)
                        details[doi] = {
                            "status": "hallucinated_not_in_graph",
                        }
        else:
            # If neo4j is not provided, compare against assigned_dois
            for doi in cited:
                if doi in assigned_set:
                    verified.append(doi)
                else:
                    hallucinated.append(doi)

        missing: list[str] = []
        if assigned_dois:
            for a in assigned_dois:
                norm_a = normalize_doi(a)
                if norm_a and norm_a not in cited:
                    missing.append(a)

        total = len(cited)
        hallucination_rate = len(hallucinated) / total if total > 0 else 0.0
        total_assigned = len(assigned_dois) if assigned_dois else (len(verified) or 1)
        coverage_rate = (len(assigned_dois) - len(missing)) / total_assigned if assigned_dois else 1.0
        is_grounded = len(hallucinated) == 0
        passed = is_grounded and len(missing) == 0

        return CitationVerificationResult(
            cited_dois=cited,
            verified_dois=verified,
            hallucinated_dois=hallucinated,
            missing_assigned_dois=missing,
            total_cited=total,
            hallucination_rate=hallucination_rate,
            coverage_rate=coverage_rate,
            is_grounded=is_grounded,
            passed=passed,
            details=details,
        )
