"""Presentation Master Service for ALRS v2.

Orchestrates fact extraction, slide generation, dialectical grounding audit,
template compilation, filesystem persistence, Neo4j graph lineage, and PDF export.
Complies with Constitution v2.2.1 (C7 static typing, C8 zero MySQL, C9 <=25 line methods, A15 compensation).
"""
from __future__ import annotations

import datetime
import logging
from pathlib import Path
from typing import Any
import uuid

from features.export.deck_generator import PresentationDeckGenerator
from features.export.fact_auditor import PresentationFactAuditor
from features.export.fact_extractor import PresentationFactExtractor
from features.export.presentation_models import (
    PresentationDeckArtifact,
    PresentationDeckRequest,
    PresentationDeckResponse,
    PresentationErrorDetail,
    PresentationErrorCode,
    PresentationSlide,
    ProjectEpistemicFacts,
    SlideGroundingCriticReport,
)
from features.export.template_engine import PresentationTemplateEngine

logger = logging.getLogger(__name__)

PERSIST_PRESENTATION_QUERY = (
    "MATCH (proj:Project {project_id: $project_id})\n"
    "MERGE (deck:PresentationDeck {deck_id: $deck_id})\n"
    "ON CREATE SET deck.project_id = $project_id, deck.audience_profile = $audience_profile, "
    "deck.theme = $theme, deck.slide_count = $slide_count, deck.file_path = $file_path, "
    "deck.file_size_bytes = $file_size_bytes, deck.sha256_hash = $sha256_hash, "
    "deck.facts_verified_count = $facts_verified_count, deck.created_at = datetime()\n"
    "MERGE (proj)-[:HAS_PRESENTATION {created_at: datetime()}]->(deck)\n"
    "WITH deck\n"
    "UNWIND $slides AS s\n"
    "MERGE (slide:PresentationSlide {slide_id: s.slide_id})\n"
    "ON CREATE SET slide.deck_id = deck.deck_id, slide.index = s.index, slide.title = s.title, "
    "slide.category = s.category, slide.layout_type = s.layout_type, "
    "slide.speaking_time_seconds = s.speaking_time_seconds, slide.created_at = datetime()\n"
    "MERGE (deck)-[:CONTAINS_SLIDE {order: s.index}]->(slide)\n"
    "WITH slide, s\n"
    "FOREACH (doi IN s.grounded_dois | "
    "MERGE (p:Paper {doi: doi}) MERGE (slide)-[:GROUNDED_IN]->(p))"
)

COMPENSATE_DECK_QUERY = (
    "MATCH (deck:PresentationDeck {deck_id: $deck_id})\n"
    "OPTIONAL MATCH (deck)-[:CONTAINS_SLIDE]->(slide:PresentationSlide)\n"
    "DETACH DELETE slide, deck"
)


class PresentationService:
    """Master orchestrator for generating, auditing, persisting, and exporting presentation decks."""

    def __init__(
        self,
        neo4j: Any,
        projects_dir: str | Path | None = None,
        log_service: Any = None,
    ) -> None:
        self.neo4j = neo4j
        self.projects_dir = Path(projects_dir or "data/campaigns")
        self.log_service = log_service
        self.extractor = PresentationFactExtractor(neo4j)
        self.generator = PresentationDeckGenerator()
        self.auditor = PresentationFactAuditor(neo4j)
        self.template_engine = PresentationTemplateEngine()

    async def generate_deck(self, request: PresentationDeckRequest) -> PresentationDeckResponse:
        """Coordinate full presentation generation and verification pipeline."""
        self._validate_request_parameters(request)
        facts = await self.extractor.extract_all_project_facts(request.project_id)
        slides = self.generator.build_slide_sequence(facts, request)
        audit_report = await self.auditor.audit_slides(request.project_id, slides)
        if not audit_report.is_grounded:
            return self._build_audit_failed_response(audit_report)
        return await self._compile_and_persist(request, facts, slides)

    def _validate_request_parameters(self, request: PresentationDeckRequest) -> None:
        """Ensure input parameters fall within sound architectural boundaries."""
        if not (8 <= request.target_slide_count <= 20):
            msg = f"{PresentationErrorCode.INVALID_SLIDE_RANGE.value}: Target slide count must be between 8 and 20"
            raise ValueError(msg)

    def _build_audit_failed_response(
        self, audit_report: SlideGroundingCriticReport
    ) -> PresentationDeckResponse:
        """Construct deterministic failure response when dialectical grounding audit fails."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        err = PresentationErrorDetail(
            code=PresentationErrorCode.GROUNDING_VERIFICATION_FAILED,
            message="Adversarial grounding verification failed: ungrounded citations detected",
            details={"violations": audit_report.violations, "chr": audit_report.measured_chr},
            recovery_guidance="Resolve ungrounded DOIs in Neo4j campaign graph before re-generating deck.",
        )
        return PresentationDeckResponse(
            success=False,
            file_path="",
            slide_count=0,
            generated_timestamp=now_iso,
            facts_verified_count=0,
            preview_html="",
            sha256_hash="",
            error=err,
        )

    async def _compile_and_persist(
        self,
        request: PresentationDeckRequest,
        facts: ProjectEpistemicFacts,
        slides: list[PresentationSlide],
    ) -> PresentationDeckResponse:
        """Render standalone HTML, write to filesystem, and persist graph lineage."""
        deck_id = f"deck-{facts.project_id}-{uuid.uuid4().hex[:8]}"
        out_path, sha_hash = self._render_and_write(request, facts, slides)
        verified_count = len(facts.scientometrics.landmark_papers) + len(facts.research_questions)
        try:
            await self.persist_presentation_to_graph(
                deck_id, request, slides, out_path, sha_hash, verified_count
            )
        except Exception as exc:
            logger.error("Failed to persist deck to Neo4j: %s. Initiating rollback.", exc)
            await self.compensate_failed_deck(deck_id)
            raise
        return self._build_success_response(out_path, slides, sha_hash, verified_count)

    def _build_success_response(
        self,
        out_path: Path,
        slides: list[PresentationSlide],
        sha_hash: str,
        verified_count: int,
    ) -> PresentationDeckResponse:
        """Construct successful PresentationDeckResponse payload."""
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return PresentationDeckResponse(
            success=True,
            file_path=str(out_path.resolve()),
            slide_count=len(slides),
            generated_timestamp=now_iso,
            facts_verified_count=verified_count,
            preview_html=slides[0].content_html if slides else "",
            sha256_hash=sha_hash,
            error=None,
        )

    def _render_and_write(
        self,
        request: PresentationDeckRequest,
        facts: ProjectEpistemicFacts,
        slides: list[PresentationSlide],
    ) -> tuple[Path, str]:
        """Compile template to standalone HTML string and write to export directory."""
        html_str = self.template_engine.render_deck(request, slides, facts)
        sha_hash = self.template_engine.calculate_sha256(html_str)
        out_path = self._write_deck_to_disk(facts.project_id, html_str)
        return out_path, sha_hash

    def _write_deck_to_disk(self, project_id: str, html_str: str) -> Path:
        """Write compiled HTML presentation to campaign exports directory."""
        export_dir = self.projects_dir / project_id / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        file_path = export_dir / f"presentation_{timestamp}.html"
        file_path.write_text(html_str, encoding="utf-8")
        return file_path

    @staticmethod
    def _map_slide_records(slides: list[PresentationSlide]) -> list[dict[str, Any]]:
        """Map presentation slide models into parameterized Cypher dictionary structures."""
        return [
            {
                "slide_id": s.slide_id,
                "index": s.index,
                "title": s.title,
                "category": s.category,
                "layout_type": s.layout_type.value,
                "speaking_time_seconds": s.presenter_notes.estimated_duration_seconds,
                "grounded_dois": s.grounding_provenance,
            }
            for s in slides
        ]

    def _build_persist_params(
        self,
        deck_id: str,
        request: PresentationDeckRequest,
        slides: list[PresentationSlide],
        file_path: Path,
        sha256_hash: str,
        verified_count: int,
    ) -> dict[str, Any]:
        """Construct parameterized payload for Cypher Query 7."""
        return {
            "project_id": request.project_id,
            "deck_id": deck_id,
            "audience_profile": request.audience_profile.value,
            "theme": request.theme.value,
            "slide_count": len(slides),
            "file_path": str(file_path.resolve()),
            "file_size_bytes": file_path.stat().st_size if file_path.exists() else 0,
            "sha256_hash": sha256_hash,
            "facts_verified_count": verified_count,
            "slides": self._map_slide_records(slides),
        }

    async def persist_presentation_to_graph(
        self,
        deck_id: str,
        request: PresentationDeckRequest,
        slides: list[PresentationSlide],
        file_path: Path,
        sha256_hash: str,
        facts_verified_count: int | None = None,
    ) -> None:
        """Execute Query 7: Persist PresentationDeck and Slide lineage into Neo4j SSOT."""
        v_count = facts_verified_count if facts_verified_count is not None else len(slides)
        params = self._build_persist_params(deck_id, request, slides, file_path, sha256_hash, v_count)
        await self.neo4j.execute_write(PERSIST_PRESENTATION_QUERY, params)

    async def compensate_failed_deck(self, deck_id: str) -> None:
        """Execute Query 8: Atomically remove transient deck and slide nodes on failure."""
        await self.neo4j.execute_write(COMPENSATE_DECK_QUERY, {"deck_id": deck_id})

    async def export_deck_to_pdf(self, html_file_path: str, output_pdf_path: str) -> str:
        """Compile presentation slides into 16:9 unclipped landscape PDF via Playwright."""
        from playwright.async_api import async_playwright

        out_path = Path(output_pdf_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto(f"file://{Path(html_file_path).resolve()}", wait_until="networkidle")
            await page.pdf(
                path=str(out_path.resolve()),
                width="16in",
                height="9in",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
            await browser.close()
        if not out_path.exists() or out_path.stat().st_size == 0:
            msg = f"{PresentationErrorCode.PERSISTENCE_ERROR.value}: Failed to generate non-empty PDF"
            raise RuntimeError(msg)
        return str(out_path.resolve())

    @staticmethod
    def _map_deck_artifact(r: dict[str, Any]) -> PresentationDeckArtifact:
        """Convert Neo4j deck record to PresentationDeckArtifact domain model."""
        fp = r.get("file_path") or ""
        return PresentationDeckArtifact(
            artifact_id=r["artifact_id"],
            project_id=r["project_id"],
            filename=Path(fp).name if fp else "presentation.html",
            file_path=fp,
            file_size_bytes=int(r.get("file_size_bytes") or 0),
            sha256_hash=r.get("sha256_hash") or "",
            slide_count=int(r.get("slide_count") or 1),
            audience_profile=r.get("audience_profile") or "supervisor",
            theme=r.get("theme") or "dark",
            facts_verified_count=int(r.get("facts_verified_count") or 0),
            created_at=r.get("created_at") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

    async def list_decks(self, project_id: str) -> list[PresentationDeckArtifact]:
        """Query Neo4j for all generated presentation decks for a project."""
        query = (
            "MATCH (proj:Project {project_id: $project_id})-[:HAS_PRESENTATION]->(d:PresentationDeck)\n"
            "RETURN d.deck_id AS artifact_id, d.project_id AS project_id, d.file_path AS file_path, "
            "d.file_size_bytes AS file_size_bytes, d.sha256_hash AS sha256_hash, "
            "d.slide_count AS slide_count, d.audience_profile AS audience_profile, "
            "d.theme AS theme, d.facts_verified_count AS facts_verified_count, "
            "toString(d.created_at) AS created_at\n"
            "ORDER BY d.created_at DESC"
        )
        records = await self.neo4j.execute_read(query, {"project_id": project_id})
        return [self._map_deck_artifact(r) for r in records]

    async def get_latest_deck(self, project_id: str) -> PresentationDeckArtifact | None:
        """Retrieve latest generated deck artifact for project."""
        decks = await self.list_decks(project_id)
        return decks[0] if decks else None

    async def get_deck_by_id(self, project_id: str, artifact_id: str) -> PresentationDeckArtifact | None:
        """Retrieve specific deck artifact by artifact_id."""
        query = (
            "MATCH (proj:Project {project_id: $project_id})-[:HAS_PRESENTATION]->(d:PresentationDeck {deck_id: $deck_id})\n"
            "RETURN d.deck_id AS artifact_id, d.project_id AS project_id, d.file_path AS file_path, "
            "d.file_size_bytes AS file_size_bytes, d.sha256_hash AS sha256_hash, "
            "d.slide_count AS slide_count, d.audience_profile AS audience_profile, "
            "d.theme AS theme, d.facts_verified_count AS facts_verified_count, "
            "toString(d.created_at) AS created_at\n"
            "LIMIT 1"
        )
        records = await self.neo4j.execute_read(query, {"project_id": project_id, "deck_id": artifact_id})
        if records:
            return self._map_deck_artifact(records[0])
        decks = await self.list_decks(project_id)
        for d in decks:
            if d.artifact_id == artifact_id:
                return d
        return None
