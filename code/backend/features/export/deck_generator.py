"""Presentation Deck Sequence Generator for ALRS v2.

Structures audience-tailored slide sequences and synthesizes contextual speaker notes.
Complies with Constitution v2.2.1 (C7 static typing, C9 <=25 line methods, 8 <= N <= 20 slides).
"""
from __future__ import annotations

import uuid
from typing import Any
import jinja2

from features.export.presentation_models import (
    PresentationAudienceProfile,
    PresentationDeckRequest,
    PresentationSlide,
    PresenterNotes,
    PresenterQuestionAnswer,
    ProjectEpistemicFacts,
    SlideLayoutType,
)
from features.export.template_engine import TEMPLATES_DIR


class PresentationDeckGenerator:
    """Generates structured, audience-tailored slide sequences with grounded presenter notes."""

    def __init__(self, templates_dir: Any = TEMPLATES_DIR) -> None:
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(templates_dir)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def build_slide_sequence(
        self, facts: ProjectEpistemicFacts, request: PresentationDeckRequest
    ) -> list[PresentationSlide]:
        """Synthesize slide sequence conforming to requested audience profile and target count."""
        archetypes = self._get_archetypes_for_audience(
            request.audience_profile, request.target_slide_count
        )
        slides: list[PresentationSlide] = []
        for idx, (layout, title, cat) in enumerate(archetypes, start=1):
            content_html, dois = self._render_slide_content(layout, facts, request)
            notes = self.synthesize_presenter_notes(layout, facts, request.audience_profile)
            slides.append(
                PresentationSlide(
                    slide_id=f"slide-{facts.project_id}-{idx}-{uuid.uuid4().hex[:6]}",
                    index=idx,
                    title=title,
                    category=cat,
                    layout_type=layout,
                    content_html=content_html,
                    presenter_notes=notes,
                    grounding_provenance=dois,
                )
            )
        return slides

    @staticmethod
    def _get_supervisor_archetypes() -> list[tuple[SlideLayoutType, str, str]]:
        """Supervisor briefing archetype sequence (up to 20 slides)."""
        return [
            (SlideLayoutType.TITLE, "Campaign Executive Overview", "Thesis Scope"),
            (SlideLayoutType.SPLIT_METRICS, "Literature Scientometrics", "Knowledge Base"),
            (SlideLayoutType.FUNNEL_DIAGRAM, "Epistemic Funnel Architecture", "Methodology"),
            (SlideLayoutType.ARCHITECTURE_SWARM, "Hierarchical Swarm Architecture", "Dual-Loop"),
            (SlideLayoutType.MATRIX_TABLE, "Section Synthesis Evidence Matrix", "Synthesis"),
            (SlideLayoutType.CITATION_NETWORK, "SVPL Multi-Hop Citation Bridges", "Discovery"),
            (SlideLayoutType.GAP_RADAR, "Research Question Frontiers", "Coverage"),
            (SlideLayoutType.QA_DISCUSSION, "Supervisor Methodology Discussion", "Discussion"),
            (SlideLayoutType.FINDINGS_GRID, "Empirical Baseline Comparisons", "Evaluation"),
            (SlideLayoutType.TWO_COLUMN_CARDS, "Architectural Trade-Off Analysis", "Design"),
            (SlideLayoutType.ROADMAP_TIMELINE, "Research Campaign Milestones", "Outlook"),
            (SlideLayoutType.MATRIX_TABLE, "Extended Dimension Synthesis", "Evidence"),
            (SlideLayoutType.CITATION_NETWORK, "Extended Pathway Analysis", "Pathways"),
            (SlideLayoutType.GAP_RADAR, "Secondary Hypothesis Evaluation", "Analysis"),
            (SlideLayoutType.FINDINGS_GRID, "Ablation & Sensitivity Findings", "Robustness"),
            (SlideLayoutType.TWO_COLUMN_CARDS, "Methodological Trade-offs", "Trade-Offs"),
            (SlideLayoutType.GAP_RADAR, "Open Research Frontiers", "Frontiers"),
            (SlideLayoutType.ROADMAP_TIMELINE, "Strategic Milestone Roadmap", "Roadmap"),
            (SlideLayoutType.QA_DISCUSSION, "Supervisor Technical Checkpoint", "Checkpoint"),
            (SlideLayoutType.TITLE, "Campaign Summary & Next Steps", "Conclusion"),
        ]

    @staticmethod
    def _get_defense_archetypes() -> list[tuple[SlideLayoutType, str, str]]:
        """Thesis defense archetype sequence (up to 20 slides)."""
        return [
            (SlideLayoutType.TITLE, "Thesis Defense Overview", "Thesis Defense"),
            (SlideLayoutType.GAP_RADAR, "Formulated Research Questions", "Problem Statement"),
            (SlideLayoutType.FUNNEL_DIAGRAM, "Epistemic Funnel Methodology", "Methodology"),
            (SlideLayoutType.ARCHITECTURE_SWARM, "Dual-Loop Multi-Agent Swarm", "Architecture"),
            (SlideLayoutType.SPLIT_METRICS, "Corpus Scientometrics & Grounding", "Knowledge Base"),
            (SlideLayoutType.MATRIX_TABLE, "Cross-Section Synthesis Matrix", "Evidence Synthesis"),
            (SlideLayoutType.CITATION_NETWORK, "SVPL Multi-Hop Discoveries", "Graph Reasoning"),
            (SlideLayoutType.FINDINGS_GRID, "Empirical Baseline Comparisons", "Evaluation"),
            (SlideLayoutType.TWO_COLUMN_CARDS, "Architectural Invariants & Trade-Offs", "Design"),
            (SlideLayoutType.QA_DISCUSSION, "Committee Technical Defense Q&A", "Evaluation"),
            (SlideLayoutType.GAP_RADAR, "Literature Coverage & Frontier Analysis", "Analysis"),
            (SlideLayoutType.MATRIX_TABLE, "Extended Dimension Synthesis", "Evidence"),
            (SlideLayoutType.CITATION_NETWORK, "Transitive Citation Topologies", "Pathways"),
            (SlideLayoutType.FINDINGS_GRID, "Ablation & Sensitivity Findings", "Robustness"),
            (SlideLayoutType.ARCHITECTURE_SWARM, "Formal Invariant Verification", "Integrity"),
            (SlideLayoutType.ROADMAP_TIMELINE, "Defense Milestones & Contributions", "Contributions"),
            (SlideLayoutType.TWO_COLUMN_CARDS, "Theoretical vs Empirical Findings", "Discussion"),
            (SlideLayoutType.SPLIT_METRICS, "Longitudinal Citation Verification", "Metrics"),
            (SlideLayoutType.QA_DISCUSSION, "Anticipated Rigor Inquiries", "Technical Defense"),
            (SlideLayoutType.TITLE, "Thesis Defense Conclusions", "Defense Summary"),
        ]

    @staticmethod
    def _get_seminar_archetypes() -> list[tuple[SlideLayoutType, str, str]]:
        """Seminar archetype sequence (up to 20 slides)."""
        return [
            (SlideLayoutType.TITLE, "Academic Seminar Presentation", "Seminar"),
            (SlideLayoutType.SPLIT_METRICS, "Literature Scientometric Overview", "Broad Context"),
            (SlideLayoutType.GAP_RADAR, "Current Research Landscape & Gaps", "Motivation"),
            (SlideLayoutType.FUNNEL_DIAGRAM, "Epistemic Review Methodology", "Methodology"),
            (SlideLayoutType.MATRIX_TABLE, "Comparative Literature Taxonomy", "Taxonomy"),
            (SlideLayoutType.CITATION_NETWORK, "Discovered Multi-Hop Pathways", "Network Analysis"),
            (SlideLayoutType.ARCHITECTURE_SWARM, "Multi-Agent Swarm Architecture", "System Design"),
            (SlideLayoutType.FINDINGS_GRID, "Empirical Literature Findings", "Findings"),
            (SlideLayoutType.TWO_COLUMN_CARDS, "Methodological Comparisons", "Comparative Analysis"),
            (SlideLayoutType.QA_DISCUSSION, "Seminar Audience Q&A Session", "Discussion"),
            (SlideLayoutType.GAP_RADAR, "Emerging Research Frontiers", "Frontiers"),
            (SlideLayoutType.MATRIX_TABLE, "Extended Synthesis Matrix", "Evidence"),
            (SlideLayoutType.CITATION_NETWORK, "Bridge Mechanism Topologies", "Citation Bridges"),
            (SlideLayoutType.ROADMAP_TIMELINE, "Ongoing Research Milestones", "Milestones"),
            (SlideLayoutType.ARCHITECTURE_SWARM, "Fast vs Slow Loop Dynamics", "Swarm Dynamics"),
            (SlideLayoutType.SPLIT_METRICS, "Venue & Author Distributions", "Scientometrics"),
            (SlideLayoutType.FINDINGS_GRID, "Key Findings Deep Dive", "Analysis"),
            (SlideLayoutType.TWO_COLUMN_CARDS, "System Design Patterns", "Patterns"),
            (SlideLayoutType.ROADMAP_TIMELINE, "Future Research Horizons", "Outlook"),
            (SlideLayoutType.QA_DISCUSSION, "Concluding Discussion & Open Q&A", "Open Q&A"),
        ]

    @staticmethod
    def _get_status_archetypes() -> list[tuple[SlideLayoutType, str, str]]:
        """Quick status archetype sequence (up to 20 slides)."""
        return [
            (SlideLayoutType.TITLE, "Sprint Status & Campaign Briefing", "Sprint Status"),
            (SlideLayoutType.SPLIT_METRICS, "Executive Scientometric Snapshot", "Key Numbers"),
            (SlideLayoutType.FUNNEL_DIAGRAM, "Pipeline Stage Progress", "Funnel Status"),
            (SlideLayoutType.GAP_RADAR, "Research Question Grounding Status", "RQ Coverage"),
            (SlideLayoutType.MATRIX_TABLE, "Active Synthesis Evidence", "Synthesis"),
            (SlideLayoutType.CITATION_NETWORK, "Recent Multi-Hop Bridges", "Bridge Discoveries"),
            (SlideLayoutType.ARCHITECTURE_SWARM, "Agent Swarm Operational Health", "Operations"),
            (SlideLayoutType.ROADMAP_TIMELINE, "Immediate Next Steps & Sprint Goals", "Sprint Goals"),
            (SlideLayoutType.FINDINGS_GRID, "Key Empirical Progress", "Deliverables"),
            (SlideLayoutType.TWO_COLUMN_CARDS, "Blockers & Risk Analysis", "Risk Assessment"),
            (SlideLayoutType.QA_DISCUSSION, "Team Standup Questions & Blockers", "Standup Q&A"),
            (SlideLayoutType.SPLIT_METRICS, "Literature Volume Changes", "Delta Metrics"),
            (SlideLayoutType.GAP_RADAR, "Open Literature Gaps", "Gaps"),
            (SlideLayoutType.MATRIX_TABLE, "Section Evidence Table", "Evidence"),
            (SlideLayoutType.ROADMAP_TIMELINE, "Upcoming Delivery Milestones", "Milestones"),
            (SlideLayoutType.ARCHITECTURE_SWARM, "Subsystem Throughput", "Performance"),
            (SlideLayoutType.TWO_COLUMN_CARDS, "Action Items & Ownership", "Action Items"),
            (SlideLayoutType.CITATION_NETWORK, "Graph Density & Bridge Metrics", "Graph Health"),
            (SlideLayoutType.FINDINGS_GRID, "Weekly Velocity & Outputs", "Velocity"),
            (SlideLayoutType.QA_DISCUSSION, "Sign-off & Decision Review", "Wrap-up"),
        ]

    def _get_archetypes_for_audience(
        self, audience: PresentationAudienceProfile, target_count: int
    ) -> list[tuple[SlideLayoutType, str, str]]:
        """Resolve ordered sequence of slide archetypes based on audience profile."""
        target = max(8, min(20, target_count))
        dispatcher = {
            PresentationAudienceProfile.SUPERVISOR: self._get_supervisor_archetypes,
            PresentationAudienceProfile.THESIS_DEFENSE: self._get_defense_archetypes,
            PresentationAudienceProfile.SEMINAR: self._get_seminar_archetypes,
            PresentationAudienceProfile.QUICK_STATUS: self._get_status_archetypes,
        }
        getter = dispatcher.get(audience, self._get_supervisor_archetypes)
        cards = getter()
        return cards[:target]

    def _render_slide_content(
        self,
        layout: SlideLayoutType,
        facts: ProjectEpistemicFacts,
        request: PresentationDeckRequest,
    ) -> tuple[str, list[str]]:
        """Render slide HTML body from modular macro and extract grounded DOIs."""
        ctx = self._build_macro_context(facts, request, layout)
        macro_name = self._resolve_macro_file(layout)
        try:
            tmpl = self.jinja_env.get_template(f"macros/{macro_name}")
            rendered = tmpl.render(ctx)
        except Exception:
            rendered = f"<div class='card'><h3>Content for {layout.value}</h3></div>"
        dois = self._collect_grounded_dois(layout, facts)
        return rendered, dois

    def _resolve_macro_file(self, layout: SlideLayoutType) -> str:
        """Map layout type to template macro filename."""
        mapping = {
            SlideLayoutType.TITLE: "slide_title.html.j2",
            SlideLayoutType.SPLIT_METRICS: "slide_metrics.html.j2",
            SlideLayoutType.FUNNEL_DIAGRAM: "slide_funnel.html.j2",
            SlideLayoutType.ARCHITECTURE_SWARM: "slide_swarm.html.j2",
            SlideLayoutType.MATRIX_TABLE: "slide_matrix.html.j2",
            SlideLayoutType.CITATION_NETWORK: "slide_citation.html.j2",
            SlideLayoutType.GAP_RADAR: "slide_gap_radar.html.j2",
            SlideLayoutType.QA_DISCUSSION: "slide_qa.html.j2",
            SlideLayoutType.FINDINGS_GRID: "slide_matrix.html.j2",
            SlideLayoutType.TWO_COLUMN_CARDS: "slide_swarm.html.j2",
            SlideLayoutType.ROADMAP_TIMELINE: "slide_funnel.html.j2",
        }
        return mapping.get(layout, "slide_title.html.j2")

    def _build_macro_context(
        self,
        facts: ProjectEpistemicFacts,
        request: PresentationDeckRequest,
        layout: SlideLayoutType,
    ) -> dict[str, Any]:
        """Construct evaluation dictionary for macro execution."""
        qa = self._generate_anticipated_qa(layout, facts)
        return {
            "project_id": facts.project_id,
            "project_name": facts.project_name,
            "domain": facts.domain,
            "description": facts.description,
            "workflow_stage": facts.workflow_stage,
            "creation_date": facts.creation_date,
            "scientometrics": facts.scientometrics.model_dump(),
            "landmark_papers": facts.scientometrics.landmark_papers,
            "synthesis_matrices": [m.model_dump() for m in facts.synthesis_matrices],
            "svpl_pathways": [p.model_dump() for p in facts.svpl_pathways],
            "research_questions": [rq.model_dump() for rq in facts.research_questions],
            "enable_mermaid": request.enable_mermaid,
            "anticipated_questions": [q.model_dump() for q in qa],
        }

    def _collect_grounded_dois(
        self, layout: SlideLayoutType, facts: ProjectEpistemicFacts
    ) -> list[str]:
        """Collect verified Neo4j DOIs associated with a slide's visual archetype."""
        if layout in [SlideLayoutType.MATRIX_TABLE, SlideLayoutType.FINDINGS_GRID]:
            return [p["doi"] for p in facts.scientometrics.landmark_papers if "doi" in p][:4]
        if layout == SlideLayoutType.CITATION_NETWORK:
            dois: list[str] = []
            for path in facts.svpl_pathways:
                dois.extend([path.from_doi, path.to_doi])
            return list(dict.fromkeys(dois))
        if layout == SlideLayoutType.TITLE and facts.scientometrics.landmark_papers:
            return [facts.scientometrics.landmark_papers[0]["doi"]]
        return []

    def synthesize_presenter_notes(
        self,
        slide_type: SlideLayoutType,
        facts: ProjectEpistemicFacts,
        audience: PresentationAudienceProfile,
    ) -> PresenterNotes:
        """Synthesize contextual talking points, estimated duration, and committee Q&A."""
        points = self._generate_talking_points(slide_type, facts, audience)
        duration = self._estimate_speaking_duration(slide_type, audience)
        qa = self._generate_anticipated_qa(slide_type, facts)
        return PresenterNotes(
            talking_points=points,
            estimated_duration_seconds=duration,
            anticipated_questions=qa,
        )

    def _generate_talking_points(
        self,
        slide_type: SlideLayoutType,
        facts: ProjectEpistemicFacts,
        audience: PresentationAudienceProfile,
    ) -> list[str]:
        """Produce 3-5 concise speaker guidance bullet points for slide narrative."""
        specific = self._talking_points_for_layout(slide_type, facts)
        if specific:
            return specific
        return self._talking_points_fallback(slide_type, audience)

    @staticmethod
    def _talking_points_for_layout(
        slide_type: SlideLayoutType, facts: ProjectEpistemicFacts
    ) -> list[str] | None:
        """Return layout-specific speaker guidance when customized."""
        if slide_type == SlideLayoutType.TITLE:
            return [
                f"Introduce research scope for campaign {facts.project_id}.",
                f"Emphasize pure Neo4j epistemic graph Single Source of Truth.",
                "Highlight Google ADK multi-agent architecture with zero citation hallucination.",
            ]
        if slide_type == SlideLayoutType.SPLIT_METRICS:
            return [
                f"Cover {facts.scientometrics.total_papers} ingested academic papers across literature.",
                f"Highlight cumulative citation count of {facts.scientometrics.total_citations}.",
                f"Explain publication distribution across {facts.scientometrics.unique_authors} unique authors.",
            ]
        if slide_type == SlideLayoutType.CITATION_NETWORK:
            return [
                "Explain the SVPL multi-hop citation bridge discovery mechanism.",
                "Detail how intermediate steiner nodes link disparate seminal papers.",
                "Verify bidirectional graph traversal integrity.",
            ]
        return None

    @staticmethod
    def _talking_points_fallback(
        slide_type: SlideLayoutType, audience: PresentationAudienceProfile
    ) -> list[str]:
        """Produce context-aware fallback talking points based on layout and audience."""
        aud_label = audience.value.replace("_", " ").title()
        return [
            f"Present core findings regarding {slide_type.value} tailored for {aud_label}.",
            "Ground claims against Neo4j citation relationships and verified evidence.",
            "Connect empirical findings directly to formulated research questions.",
        ]

    def _estimate_speaking_duration(
        self, slide_type: SlideLayoutType, audience: PresentationAudienceProfile
    ) -> int:
        """Estimate recommended speaking time in seconds (30s <= time <= 300s)."""
        if slide_type in [SlideLayoutType.MATRIX_TABLE, SlideLayoutType.CITATION_NETWORK]:
            return 150 if audience == PresentationAudienceProfile.THESIS_DEFENSE else 120
        if slide_type == SlideLayoutType.TITLE:
            return 60
        return 90

    def _generate_anticipated_qa(
        self, slide_type: SlideLayoutType, facts: ProjectEpistemicFacts
    ) -> list[PresenterQuestionAnswer]:
        """Produce anticipated challenging questions with graph-grounded model answers."""
        if slide_type == SlideLayoutType.CITATION_NETWORK:
            return [
                PresenterQuestionAnswer(
                    question="How are multi-hop citation bridges verified against false positives?",
                    model_answer="Through semantic vector cosine similarity combined with topological Steiner tree constraints in Neo4j.",
                )
            ]
        if slide_type == SlideLayoutType.SPLIT_METRICS:
            return [
                PresenterQuestionAnswer(
                    question="Why do citation counts aggregate across cited_by_count?",
                    model_answer="cited_by_count reflects canonical OpenAlex citations, avoiding out-of-graph undercounting.",
                )
            ]
        return [
            PresenterQuestionAnswer(
                question="How does this slide align with the thesis research questions?",
                model_answer="Directly addresses formulated RQs by querying grounded epistemic nodes in Neo4j SSOT.",
            )
        ]
