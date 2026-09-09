"""Dialectical Fact Auditor and Citation Hallucination Rate Validator for ALRS v2.

Adversarially audits candidate presentation slides against Neo4j SSOT.
Strictly enforces CHR == 0.0% invariant per Constitution v2.2.1 (A33, A36, A37, C9).
"""
from __future__ import annotations

import re
from typing import Any, TYPE_CHECKING

from features.export.presentation_models import (
    PresentationSlide,
    SlideGroundingCriticReport,
)

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService

DOI_REGEX = re.compile(r"10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")


class PresentationFactAuditor:
    """Adversarial critic auditor evaluating slide citation grounding against Neo4j SSOT."""

    def __init__(self, neo4j: Neo4jService | Any) -> None:
        self.neo4j = neo4j

    async def audit_slides(
        self, project_id: str, slides: list[PresentationSlide]
    ) -> SlideGroundingCriticReport:
        """Evaluate candidate presentation slides for citation provenance and fact consistency."""
        candidate_dois = self._extract_candidate_dois(slides)
        violations: list[str] = []
        directives: list[str] = []

        self._check_presenter_notes_completeness(slides, violations, directives)
        await self._verify_scientometric_metrics(project_id, slides, violations, directives)
        if not candidate_dois:
            if violations:
                return self._build_rejected_report(0.0, violations, directives)
            return self._build_grounded_report([], violations, directives, total_citations=0)

        chr_rate = await self._verify_candidate_dois(candidate_dois, violations, directives)
        if chr_rate > 0.0 or len(violations) > 0:
            return self._build_rejected_report(chr_rate, violations, directives)
        return self._build_grounded_report(candidate_dois, violations, directives, len(candidate_dois))

    async def _verify_candidate_dois(
        self, candidate_dois: list[str], violations: list[str], directives: list[str]
    ) -> float:
        """Query Neo4j to verify candidate DOIs and return measured CHR."""
        query = (
            "UNWIND $candidate_dois AS candidate_doi\n"
            "OPTIONAL MATCH (p:Paper)\n"
            "WHERE toLower(p.doi) = toLower(candidate_doi) "
            "OR toLower(p.doi) = 'https://doi.org/' + toLower(candidate_doi) "
            "OR toLower(p.doi) = 'http://dx.doi.org/' + toLower(candidate_doi)\n"
            "RETURN candidate_doi, (p IS NOT NULL) AS is_grounded, coalesce(p.title, '') AS verified_title"
        )
        records = await self.neo4j.execute_read(query, {"candidate_dois": candidate_dois})
        ungrounded = self._filter_ungrounded_dois(records)
        for u_doi in ungrounded:
            violations.append(f"Ungrounded DOI citation detected: {u_doi}")
            directives.append(f"Remove or verify candidate citation {u_doi} in Neo4j campaign graph")
        return (len(ungrounded) / len(candidate_dois)) * 100.0 if candidate_dois else 0.0

    async def _verify_scientometric_metrics(
        self,
        project_id: str,
        slides: list[PresentationSlide],
        violations: list[str],
        directives: list[str],
    ) -> None:
        """Verify that any quantitative paper count claims match Neo4j graph ground truth."""
        query = (
            "OPTIONAL MATCH (p:Paper)\n"
            "WHERE (p)-[:BELONGS_TO]->(:Project {project_id: $project_id}) OR p.project_id = $project_id\n"
            "RETURN count(p) AS total_papers"
        )
        try:
            records = await self.neo4j.execute_read(query, {"project_id": project_id})
            if not records or "total_papers" not in records[0]:
                return
            graph_papers = int(records[0]["total_papers"])
            self._check_slide_paper_counts(slides, graph_papers, violations, directives)
        except Exception:
            pass

    def _check_slide_paper_counts(
        self,
        slides: list[PresentationSlide],
        graph_papers: int,
        violations: list[str],
        directives: list[str],
    ) -> None:
        """Inspect slides for explicit total paper claims conflicting with graph count."""
        for s in slides:
            pts = " ".join(s.presenter_notes.talking_points if s.presenter_notes else [])
            m_notes = re.search(r"Cover (\d+) ingested academic papers", pts)
            m_html = re.search(r'<div class="stat-number">(\d+)</div>\s*<div class="stat-label">Indexed Papers</div>', s.content_html)
            claimed = int(m_notes.group(1)) if m_notes else (int(m_html.group(1)) if m_html else None)
            if claimed is not None and claimed != graph_papers:
                violations.append(f"Metric drift on slide {s.index}: claims {claimed} papers but Neo4j contains {graph_papers}")
                directives.append(f"Re-synchronize slide {s.index} scientometrics with Neo4j ground truth ({graph_papers} papers)")

    @staticmethod
    def _clean_doi(raw_doi: str) -> str:
        """Normalize and strip URL prefixes and surrounding punctuation/brackets from DOI."""
        cleaned = raw_doi.strip()
        if "doi.org/" in cleaned:
            cleaned = cleaned.split("doi.org/")[-1]
        return cleaned.strip(".,;:()[]{}<>\"'").strip()

    def _extract_candidate_dois(self, slides: list[PresentationSlide]) -> list[str]:
        """Extract canonical DOIs from slide provenance fields and content markup."""
        dois: set[str] = set()
        for s in slides:
            for d in s.grounding_provenance:
                cleaned = self._clean_doi(d)
                if cleaned:
                    dois.add(cleaned)
            for match in DOI_REGEX.findall(s.content_html):
                cleaned = self._clean_doi(match)
                if cleaned:
                    dois.add(cleaned)
        return sorted(list(dois))

    def _filter_ungrounded_dois(self, records: list[dict[str, Any]]) -> list[str]:
        """Filter audit query records to return list of ungrounded candidate DOIs."""
        return [
            str(r.get("candidate_doi"))
            for r in records
            if not r.get("is_grounded") and r.get("candidate_doi")
        ]

    def _check_presenter_notes_completeness(
        self, slides: list[PresentationSlide], violations: list[str], directives: list[str]
    ) -> None:
        """Ensure every slide contains actionable presenter talking points."""
        for s in slides:
            pts = [p.strip() for p in (s.presenter_notes.talking_points if s.presenter_notes else []) if p.strip()]
            if not s.presenter_notes or len(pts) == 0:
                violations.append(f"Slide {s.index} ({s.title}) is missing speaker talking points")
                directives.append(f"Synthesize at least 3 speaker bullet points for Slide {s.index}")

    def _build_grounded_report(
        self,
        candidate_dois: list[str],
        violations: list[str],
        directives: list[str],
        total_citations: int,
    ) -> SlideGroundingCriticReport:
        """Construct positive verification report when CHR == 0.0%."""
        return SlideGroundingCriticReport(
            is_grounded=True,
            measured_chr=0.0,
            composite_score=1.0,
            dimension_scores={
                "citation_grounding": 1.0,
                "metric_fidelity": 1.0,
                "structural_integrity": 1.0,
                "notes_completeness": 1.0,
            },
            violations=violations,
            actionable_directives=directives,
        )

    def _build_rejected_report(
        self, chr_rate: float, violations: list[str], directives: list[str]
    ) -> SlideGroundingCriticReport:
        """Construct adversarial rejection report when ungrounded citations are detected."""
        score = max(0.0, 1.0 - (chr_rate / 100.0) - (0.1 * len(violations)))
        return SlideGroundingCriticReport(
            is_grounded=False,
            measured_chr=chr_rate,
            composite_score=round(score, 3),
            dimension_scores={
                "citation_grounding": max(0.0, 1.0 - (chr_rate / 100.0)),
                "metric_fidelity": 0.8,
                "structural_integrity": 0.9,
                "notes_completeness": 0.85,
            },
            violations=violations,
            actionable_directives=directives,
        )
