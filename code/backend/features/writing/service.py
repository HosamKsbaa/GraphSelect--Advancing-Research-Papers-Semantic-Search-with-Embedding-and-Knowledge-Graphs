"""Writing service for literature review drafting and review in ALRS v2.

Extracted business logic for paper abstract retrieval, section drafting,
and section review.  Used by both ADK tool wrappers and FastAPI router
endpoints.

Functions:
    - get_paper_abstracts: batch-fetch abstracts by DOI list
    - draft_section: LLM-driven section drafting with citations
    - review_section: LLM-driven section review with structured feedback
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService
    from core.llm.service import LLMService
    from core.logging.log_service import LogService

logger = logging.getLogger(__name__)


class WritingService:
    """Drafting and review service for literature-review sections.

    Attributes:
        _neo4j: Injected Neo4j graph database service.
        _llm: Injected LLM completion service.
        _log_service: Optional logging service for telemetry.
        _projects_dir: Root directory for per-project artifacts.
    """

    def __init__(
        self,
        neo4j: Neo4jService | None = None,
        llm: LLMService | None = None,
        log_service: LogService | None = None,
        projects_dir: str = "projects",
    ) -> None:
        self._neo4j = neo4j
        self._llm = llm
        self._log_service = log_service
        self._projects_dir = projects_dir

    # ------------------------------------------------------------------
    # T044 – get_paper_abstracts
    # ------------------------------------------------------------------

    async def get_paper_abstracts(
        self,
        project_id: str,
        dois: list[str],
    ) -> dict[str, Any]:
        """Retrieve abstracts for a list of papers to provide writing context.

        Only DOIs that exist in the graph are returned with full metadata.

        Args:
            project_id: The project UUID (for logging).
            dois: List of DOI strings to look up.

        Returns:
            A dict with key 'papers' — a list of dicts each containing
            doi, title, abstract, year, and source.
        """
        if not dois:
            return {"papers": [], "message": "No DOIs provided."}

        neo4j = self._neo4j
        if neo4j is None:
            return {"papers": [], "message": "Neo4j service not available."}
        results: list[dict[str, Any]] = []

        for doi in dois:
            paper = await neo4j.get_paper_by_doi(doi)
            if paper:
                results.append({
                    "doi": paper.get("doi", doi),
                    "title": paper.get("title", ""),
                    "abstract": paper.get("abstract") or "Abstract not available.",
                    "year": paper.get("year"),
                    "source": paper.get("source"),
                })
            else:
                results.append({
                    "doi": doi,
                    "title": "Unknown",
                    "abstract": "Paper not found in the knowledge graph.",
                    "year": None,
                    "source": None,
                })

        if self._log_service and project_id:
            await self._log_service.log_agent_trace(
                project_id=project_id,
                agent_name="DraftingAgent",
                event_type="tool_call",
                details={
                    "tool": "get_paper_abstracts",
                    "requested": len(dois),
                    "found": sum(1 for r in results if r["title"] != "Unknown"),
                },
            )

        return {"papers": results}

    # ------------------------------------------------------------------
    # T045 – draft_section
    # ------------------------------------------------------------------

    async def draft_section(
        self,
        project_id: str,
        section_title: str,
        section_description: str,
        paper_dois: list[str],
        target_level: str = "master",
        outline_context: str | None = None,
    ) -> dict[str, Any]:
        """Draft a single section of the literature review using the LLM.

        Generates a Markdown section with inline citations.  The draft is
        persisted to ``{projects_dir}/{project_id}/drafts/{slug}.md``.

        Args:
            project_id: The project UUID.
            section_title: The heading for this section.
            section_description: 2-3 sentence description of the section's scope.
            paper_dois: List of DOIs assigned to this section.
            target_level: Academic level — 'master' or 'phd'.
            outline_context: Optional additional context from the outline.

        Returns:
            A dict with keys: section_title, markdown, word_count,
            cited_dois, saved_path.
        """
        from core.llm.models import CompletionRequest

        neo4j = self._neo4j
        llm = self._llm
        if llm is None:
            raise RuntimeError("LLM service not configured.")

        # Fetch paper details for the prompt
        paper_blocks: list[str] = []
        for doi in paper_dois:
            paper = await neo4j.get_paper_by_doi(doi) if neo4j is not None else None
            if paper:
                abstract_text = (paper.get("abstract") or "No abstract available.")[:600]
                paper_blocks.append(
                    f"[{doi}]\n"
                    f"  Title: {paper.get('title', 'Unknown')}\n"
                    f"  Year: {paper.get('year', 'N/A')}\n"
                    f"  Abstract: {abstract_text}"
                )
            else:
                paper_blocks.append(f"[{doi}]\n  Title: Unknown\n  Year: N/A")

        papers_text = "\n\n".join(paper_blocks) if paper_blocks else "No source papers available."

        level_guidance = (
            "Write at a level suitable for a master's thesis. "
            "Use clear, accessible academic language."
            if target_level == "master"
            else "Write at a level suitable for a doctoral dissertation. "
            "Use sophisticated academic language and deeper critical analysis."
        )

        prompt = f"""You are an expert academic writer preparing a literature review section.

## Section
Title: {section_title}
Description: {section_description}

## Source Papers
{papers_text}

## Requirements
1. {level_guidance}
2. Write 400-800 words in Markdown format.
3. Start with a brief introduction to the section's theme.
4. Synthesise — do NOT just summarise papers one-by-one.  Compare,
   contrast, and identify patterns across sources.
5. Use inline citations in the format ``(AuthorLastName, Year)`` where
   Author is derived from the paper title/DOI context.  If the author
   name is unknown, use ``(DOI: <short-doi>)`` instead.
6. End with a brief transition sentence leading to the next section.
7. Do NOT include section numbers or the word "Section" in the heading.
8. Output ONLY the Markdown text.  Do not add meta-commentary.
"""

        request = CompletionRequest(
            prompt=prompt,
            system_instruction="You are an academic writing assistant. Produce only the requested Markdown.",
            temperature=0.5,
            max_tokens=4096,
        )

        response = await llm.complete(request)
        markdown: str = response.text.strip()

        # Count words
        word_count: int = len(markdown.split())

        # Determine which DOIs were actually cited
        cited_dois: list[str] = [doi for doi in paper_dois if doi in markdown]

        # Save to disk with cross-platform fallback
        from core.storage_utils import get_safe_project_dir, safe_write_text
        slug = re.sub(r"[^a-z0-9]+", "_", section_title.lower()).strip("_")[:60]
        draft_dir = get_safe_project_dir(project_id, subfolder="drafts", primary_base=self._projects_dir)
        draft_path = draft_dir / f"{slug}.md"
        actual_path, _ = safe_write_text(draft_path, markdown, encoding="utf-8")

        # Log trace
        if self._log_service:
            await self._log_service.log_agent_trace(
                project_id=project_id,
                agent_name="DraftingAgent",
                event_type="tool_call",
                token_count=response.usage.total_tokens,
                details={
                    "tool": "draft_section",
                    "section": section_title,
                    "word_count": word_count,
                    "cited_dois": len(cited_dois),
                },
            )

        return {
            "section_title": section_title,
            "markdown": markdown,
            "word_count": word_count,
            "cited_dois": cited_dois,
            "saved_path": str(actual_path),
        }

    # ------------------------------------------------------------------
    # ------------------------------------------------------------------
    # Citation Verification
    # ------------------------------------------------------------------

    async def verify_citations(
        self,
        project_id: str,
        draft_text: str,
        assigned_dois: list[str] | None = None,
    ) -> dict[str, Any]:
        """Verify citations in draft text against Neo4j knowledge graph.

        Args:
            project_id: The project UUID.
            draft_text: The full draft text.
            assigned_dois: Optional list of DOIs that should be cited.

        Returns:
            Dict containing verified, hallucinated, and missing citations.
        """
        from agents.writing.citation_verifier import CitationVerifier

        verifier = CitationVerifier(self._neo4j)
        result = await verifier.verify_text_citations(
            text=draft_text,
            project_id=project_id,
            assigned_dois=assigned_dois,
        )
        return result.to_dict()

    # ------------------------------------------------------------------
    # T046 – review_section
    # ------------------------------------------------------------------

    async def review_section(
        self,
        project_id: str,
        section_title: str,
        draft_text: str,
        paper_dois: list[str],
        target_level: str = "master",
    ) -> dict[str, Any]:
        """Review a drafted section for accuracy, completeness, and coherence.

        Evaluates the section against academic standards, checking citation
        coverage, logical flow, synthesis quality, and factual consistency
        with the source papers. Also runs deterministic citation verification
        to detect and reject hallucinated citations.

        Args:
            project_id: The project UUID (for logging).
            section_title: Title of the section being reviewed.
            draft_text: The full Markdown text of the draft.
            paper_dois: List of DOIs that should be cited in this section.
            target_level: Academic level — 'master' or 'phd'.

        Returns:
            A dict with keys:
            - approved (bool): True if the section meets quality standards.
            - feedback (list[str]): Specific improvement suggestions.
            - missing_citations (list[str]): DOIs assigned but not cited.
            - hallucinated_citations (list[str]): Cited DOIs not in knowledge graph.
            - scores (dict): Sub-scores for coverage, coherence, synthesis, tone, completeness.
            - citation_verification (dict): Full citation verification metrics.
        """
        from core.llm.models import CompletionRequest
        from agents.writing.citation_verifier import CitationVerifier

        llm = self._llm
        if llm is None:
            raise RuntimeError("LLM service not configured.")

        # Run deterministic citation verification against Neo4j
        verifier = CitationVerifier(self._neo4j)
        ver_result = await verifier.verify_text_citations(
            text=draft_text,
            project_id=project_id,
            assigned_dois=paper_dois,
        )

        missing_citations: list[str] = ver_result.missing_assigned_dois
        hallucinated_citations: list[str] = ver_result.hallucinated_dois

        prompt = f"""You are an expert academic reviewer evaluating a literature review section.

## Section Title
{section_title}

## Draft
{draft_text}

## Assigned Papers (DOIs)
{json.dumps(paper_dois)}

## Missing Citations (DOIs assigned but NOT appearing in draft)
{json.dumps(missing_citations)}

## Hallucinated / Unverified Citations (DOIs cited but NOT in knowledge graph)
{json.dumps(hallucinated_citations)}

## Evaluation Criteria
Rate each criterion on a scale of 1-5 and provide specific feedback:
1. **Citation Coverage** — Are all assigned papers cited and discussed? Are there any unverified citations?
2. **Coherence** — Does the section flow logically? Are transitions smooth?
3. **Synthesis Quality** — Does the section synthesise across papers
   (comparing, contrasting, identifying patterns) rather than summarising
   each paper individually?
4. **Academic Tone** — Is the writing appropriate for an academic
   literature review?
5. **Completeness** — Is the section thorough enough (typically 400-800 words)?

## Response Format
Respond in valid JSON:
{{
  "approved": true/false,
  "scores": {{
    "citation_coverage": 1-5,
    "coherence": 1-5,
    "synthesis": 1-5,
    "academic_tone": 1-5,
    "completeness": 1-5
  }},
  "feedback": ["specific suggestion 1", "specific suggestion 2", ...],
  "missing_citations": ["doi1", ...]
}}

Set "approved" to true ONLY if ALL scores are >= 4 AND there are no
missing citations AND there are no hallucinated citations.
"""

        request = CompletionRequest(
            prompt=prompt,
            system_instruction=(
                "You are a strict academic reviewer. "
                "Respond ONLY with valid JSON matching the requested schema."
            ),
            temperature=0.3,
            max_tokens=2048,
            response_format="application/json",
        )

        response = await llm.complete(request)
        raw_text = response.text.strip()

        # Strip markdown code fences
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw_text = "\n".join(lines).strip()

        try:
            review_data: dict[str, Any] = json.loads(raw_text)
        except json.JSONDecodeError:
            review_data = {
                "approved": False,
                "scores": {},
                "feedback": [
                    "Review parsing failed. Please revise the section and try again.",
                    f"Raw reviewer output: {raw_text[:500]}",
                ],
                "missing_citations": missing_citations,
            }

        # Ensure missing_citations from our pre-check are included
        review_missing = review_data.get("missing_citations", [])
        all_missing = list(set(missing_citations + review_missing)) if missing_citations or review_missing else []
        review_data["missing_citations"] = review_missing if review_missing is not None else all_missing
        review_data["hallucinated_citations"] = hallucinated_citations
        review_data["citation_verification"] = ver_result.to_dict()

        # Normalize scores to both top-level and 'scores' dict
        scores = review_data.get("scores", {})
        if not isinstance(scores, dict) or not scores:
            scores = {
                "citation_coverage": review_data.get("citation_coverage", 5),
                "coherence": review_data.get("coherence", 5),
                "synthesis": review_data.get("synthesis", 5),
                "academic_tone": review_data.get("academic_tone", 5),
                "completeness": review_data.get("completeness", 5),
            }
            review_data["scores"] = scores
        for k in ["citation_coverage", "coherence", "synthesis", "academic_tone", "completeness"]:
            if k in scores:
                review_data[k] = scores[k]
            elif k in review_data:
                scores[k] = review_data[k]

        feedback_list: list[str] = list(review_data.get("feedback", []))

        # Enforce zero-hallucination policy: any ungrounded DOI forces approval to False
        if hallucinated_citations:
            feedback_list.append(
                f"Hallucinated citation(s) detected: {', '.join(hallucinated_citations)}. "
                "These citations do not exist in the project knowledge graph and must be removed or replaced."
            )
            review_data["approved"] = False
            scores["citation_coverage"] = min(scores.get("citation_coverage", 5), 2)
            review_data["citation_coverage"] = scores["citation_coverage"]
            review_data["scores"] = scores

        review_data["feedback"] = feedback_list

        # Log trace
        if self._log_service and project_id:
            await self._log_service.log_agent_trace(
                project_id=project_id,
                agent_name="ReviewerAgent",
                event_type="tool_call",
                token_count=response.usage.total_tokens,
                details={
                    "tool": "review_section",
                    "section": section_title,
                    "approved": review_data.get("approved", False),
                    "scores": review_data.get("scores", {}),
                    "hallucinated_count": len(hallucinated_citations),
                },
            )

        return review_data

