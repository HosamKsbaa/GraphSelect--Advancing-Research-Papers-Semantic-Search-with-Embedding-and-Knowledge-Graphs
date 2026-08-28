"""Planning service for outline generation in ALRS v2.

Extracted business logic for project summary inspection and
LLM-driven outline generation.  Used by both ADK tool wrappers
and FastAPI router endpoints.

Functions:
    - get_project_summary: overview of papers, questions, gaps
    - generate_outline: LLM-driven outline generation with paper assignments
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService
    from core.llm.service import LLMService

logger = logging.getLogger(__name__)


class PlanningService:
    """Outline planning service for literature-review projects.

    Attributes:
        _neo4j: Injected Neo4j graph database service.
        _llm: Injected LLM completion service.
        _projects_dir: Root directory for per-project artifacts.
    """

    def __init__(
        self,
        neo4j: Neo4jService,
        llm: LLMService,
        projects_dir: str = "projects",
    ) -> None:
        self._neo4j = neo4j
        self._llm = llm
        self._projects_dir = projects_dir

    # ------------------------------------------------------------------
    # T039 – get_project_summary
    # ------------------------------------------------------------------

    async def get_project_summary(
        self,
        project_id: str,
    ) -> dict[str, Any]:
        """Get a summary of the project's current state for planning.

        Returns paper_count, question_count, gap_count, has_outline,
        has_drafts, and a list of research question texts.

        Args:
            project_id: The project UUID.

        Returns:
            A dict with keys: project_id, paper_count, question_count,
            gap_count, has_outline, has_drafts, questions.
        """
        neo4j = self._neo4j

        # Count papers linked to the project
        papers = await neo4j.get_project_papers(project_id, limit=9999)
        paper_count: int = len(papers)

        # Count research questions
        questions = await neo4j.get_research_questions(project_id)
        question_count: int = len(questions)
        question_texts: list[str] = [q.get("text", "") for q in questions]

        # Detect gaps: questions with no highly-similar papers
        gap_count: int = 0
        if questions and papers:
            try:
                sims = await neo4j.execute_read(
                    """
                    MATCH (q:ResearchQuestion {project_id: $pid})
                    OPTIONAL MATCH (pr:Project {project_id: $pid})-[:HAS_PAPER]->(p:Paper)
                    WHERE q.embedding IS NOT NULL AND p.embedding IS NOT NULL
                    WITH q, count(p) AS linked
                    WHERE linked = 0
                    RETURN count(q) AS gap_count
                    """,
                    {"pid": project_id},
                )
                gap_count = int(sims[0].get("gap_count", 0)) if sims else 0
            except Exception:
                gap_count = 0

        # Check for existing outlines / drafts on disk
        project_dir = Path(self._projects_dir) / project_id
        has_outline: bool = (project_dir / "outlines").exists() and any(
            (project_dir / "outlines").iterdir()
        ) if (project_dir / "outlines").exists() else False
        has_drafts: bool = (project_dir / "drafts").exists() and any(
            (project_dir / "drafts").iterdir()
        ) if (project_dir / "drafts").exists() else False

        return {
            "project_id": project_id,
            "paper_count": paper_count,
            "question_count": question_count,
            "gap_count": gap_count,
            "has_outline": has_outline,
            "has_drafts": has_drafts,
            "questions": question_texts,
        }

    # ------------------------------------------------------------------
    # T040 – generate_outline
    # ------------------------------------------------------------------

    async def generate_outline(
        self,
        project_id: str,
        style: str = "thematic",
        num_sections: int | None = None,
    ) -> dict[str, Any]:
        """Generate a structured literature review outline.

        Uses the LLM to create thematic or chronological sections, each with
        assigned papers and descriptive summaries.  The result is saved to
        ``{projects_dir}/{project_id}/outlines/outline.json``.

        Args:
            project_id: The project UUID.
            style: Outline style — 'thematic', 'chronological', or
                   'methodological'.
            num_sections: Optional hint for the number of sections.

        Returns:
            A dict with keys: sections, narrative_arc, style, saved_path.
        """
        from core.llm.models import CompletionRequest

        neo4j = self._neo4j
        llm = self._llm

        # Gather inputs
        questions = await neo4j.get_research_questions(project_id)
        question_texts = [q.get("text", "") for q in questions]

        # Get papers for the LLM prompt
        papers = await neo4j.get_project_papers(project_id, limit=100)
        paper_summaries: list[str] = []
        for p in papers:
            abstract_preview = (p.get("abstract") or "No abstract")[:300]
            paper_summaries.append(
                f"- DOI: {p.get('doi')}\n"
                f"  Title: {p.get('title')}\n"
                f"  Year: {p.get('year')}\n"
                f"  Abstract: {abstract_preview}"
            )

        papers_block = "\n".join(paper_summaries) if paper_summaries else "No papers available."
        questions_block = "\n".join(f"- {q}" for q in question_texts) if question_texts else "No research questions."

        section_range = f"{num_sections}" if num_sections else "3-6"

        prompt = f"""You are an expert academic literature review planner.

Given the following research questions and collected papers, generate a structured
outline for a literature review using a **{style}** organisation style.

## Research Questions
{questions_block}

## Available Papers (ranked by relevance)
{papers_block}

## Instructions
1. Create {section_range} coherent sections that cover the research questions.
2. For each section provide:
   - "title": A clear section heading.
   - "description": 2-3 sentences describing what the section covers.
   - "assigned_papers": A list of DOIs from the papers above that should be discussed.
   - "theme": The overarching theme or keyword.
3. Provide a "narrative_arc" field describing the logical flow from section 1 to the last.
4. Respond in valid JSON with this schema:
{{
  "sections": [
    {{
      "title": "...",
      "description": "...",
      "assigned_papers": ["doi1", "doi2"],
      "theme": "..."
    }}
  ],
  "narrative_arc": "..."
}}
"""

        request = CompletionRequest(
            prompt=prompt,
            system_instruction=(
                "You are a research planning assistant. "
                "Respond ONLY with valid JSON matching the requested schema."
            ),
            temperature=0.4,
            max_tokens=8192,
            response_format="application/json",
        )

        response = await llm.complete(request)
        raw_text = response.text.strip()

        # Strip markdown code fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw_text = "\n".join(lines).strip()

        try:
            outline_data: dict[str, Any] = json.loads(raw_text)
        except json.JSONDecodeError:
            return {"error": "LLM returned invalid JSON for outline.", "raw": raw_text[:1000]}

        # Persist to disk with cross-platform fallback
        from core.storage_utils import get_safe_project_dir, safe_write_text
        project_dir = get_safe_project_dir(project_id, subfolder="outlines", primary_base=self._projects_dir)
        outline_path = project_dir / "outline.json"
        actual_path, _ = safe_write_text(outline_path, json.dumps(outline_data, indent=2, ensure_ascii=False))

        return {
            "sections": outline_data.get("sections", []),
            "narrative_arc": outline_data.get("narrative_arc", ""),
            "style": style,
            "saved_path": str(actual_path),
        }
