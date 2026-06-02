"""Outline planning tools for the PlannerAgent.

Provides tools to inspect project state, retrieve ranked papers,
and generate structured literature-review outlines using the LLM.

Tools:
    - get_project_summary: overview of papers, questions, gaps
    - get_ranked_papers: hybrid-scored paper list for outline planning
    - generate_outline: LLM-driven outline generation with paper assignments
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import registry
from config import get_settings
from core.llm.models import CompletionRequest

logger = logging.getLogger(__name__)


# ------------------------------------------------------------------
# T039 – get_project_summary
# ------------------------------------------------------------------

async def get_project_summary(tool_context: ToolContext) -> dict[str, Any]:
    """Get a summary of the project's current state for planning.

    Returns paper_count, question_count, gap_count, has_outline,
    has_drafts, and a list of research question texts. The agent
    should call this first to understand the project before
    generating an outline.

    Returns:
        A dict with keys: project_id, paper_count, question_count,
        gap_count, has_outline, has_drafts, questions.
    """
    project_id: str = tool_context.state.get("project_id", "")
    if not project_id:
        return {"error": "No project_id found in session state."}

    neo4j = registry.neo4j
    settings = get_settings()

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
            # Use the first session-like pattern if available
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
    project_dir = Path(settings.projects_dir) / project_id
    has_outline: bool = (project_dir / "outlines").exists() and any(
        (project_dir / "outlines").iterdir()
    ) if (project_dir / "outlines").exists() else False
    has_drafts: bool = (project_dir / "drafts").exists() and any(
        (project_dir / "drafts").iterdir()
    ) if (project_dir / "drafts").exists() else False

    summary: dict[str, Any] = {
        "project_id": project_id,
        "paper_count": paper_count,
        "question_count": question_count,
        "gap_count": gap_count,
        "has_outline": has_outline,
        "has_drafts": has_drafts,
        "questions": question_texts,
    }

    # Log the action
    if registry.log_service:
        await registry.log_service.log_agent_trace(
            project_id=project_id,
            agent_name="PlannerAgent",
            event_type="tool_call",
            details={"tool": "get_project_summary", "summary": summary},
        )

    return summary


# ------------------------------------------------------------------
# T041 – get_ranked_papers
# ------------------------------------------------------------------

async def get_ranked_papers(tool_context: ToolContext) -> dict[str, Any]:
    """Retrieve ranked papers for outline generation using hybrid scoring.

    Combines semantic similarity (against research questions) and
    PageRank centrality in the citation graph. Papers are returned
    in descending order of a combined score.

    Returns:
        A dict with key 'papers' containing a list of dicts, each
        with: doi, title, abstract, year, similarity_score,
        pagerank_score, combined_score.
    """
    project_id: str = tool_context.state.get("project_id", "")
    if not project_id:
        return {"error": "No project_id found in session state."}

    neo4j = registry.neo4j

    # Fetch all project papers
    papers = await neo4j.get_project_papers(project_id, limit=200)
    if not papers:
        return {"papers": [], "message": "No papers found in the project."}

    # Compute PageRank scores (uses session_id pattern — we map project→session)
    # Try direct subgraph approach
    pagerank_scores: dict[str, float] = {}
    try:
        pr_query = """
        MATCH (pr:Project {project_id: $pid})-[:HAS_PAPER]->(p1:Paper)-[:CITES]->(p2:Paper)
        WHERE (pr)-[:HAS_PAPER]->(p2)
        RETURN p1.doi AS source, p2.doi AS target
        """
        edge_records = await neo4j.execute_read(pr_query, {"pid": project_id})

        node_query = """
        MATCH (pr:Project {project_id: $pid})-[:HAS_PAPER]->(p:Paper)
        RETURN p.doi AS doi
        """
        node_records = await neo4j.execute_read(node_query, {"pid": project_id})
        dois = [str(r["doi"]) for r in node_records if r.get("doi")]

        if dois:
            try:
                import networkx as nx

                g = nx.DiGraph()
                g.add_nodes_from(dois)
                for r in edge_records:
                    if r.get("source") and r.get("target"):
                        g.add_edge(str(r["source"]), str(r["target"]))
                raw_pr = nx.pagerank(g, alpha=0.85, max_iter=20)
                # Normalize to [0, 1]
                if raw_pr:
                    min_s = min(raw_pr.values())
                    max_s = max(raw_pr.values())
                    diff = max_s - min_s
                    if diff > 0.0:
                        pagerank_scores = {k: (v - min_s) / diff for k, v in raw_pr.items()}
                    else:
                        pagerank_scores = {k: 1.0 for k in raw_pr}
            except ImportError:
                logger.warning("networkx not available; skipping PageRank scoring")
    except Exception as exc:
        logger.warning("PageRank computation failed: %s", exc)

    # Compute similarity scores between papers and questions
    similarity_scores: dict[str, float] = {}
    try:
        sim_query = """
        MATCH (q:ResearchQuestion {project_id: $pid})
        WHERE q.embedding IS NOT NULL
        MATCH (pr:Project {project_id: $pid})-[:HAS_PAPER]->(p:Paper)
        WHERE p.embedding IS NOT NULL
        WITH p, q,
             gds.similarity.cosine(p.embedding, q.embedding) AS sim
        RETURN p.doi AS doi, max(sim) AS max_similarity
        """
        sim_records = await neo4j.execute_read(sim_query, {"pid": project_id})
        for r in sim_records:
            if r.get("doi"):
                similarity_scores[str(r["doi"])] = float(r.get("max_similarity", 0.0))
    except Exception:
        # Fallback: try vector index approach or skip similarity
        logger.warning("Similarity computation failed; using uniform scores")

    # Combine scores: 60% similarity + 40% PageRank
    SIM_WEIGHT = 0.6
    PR_WEIGHT = 0.4

    ranked: list[dict[str, Any]] = []
    for paper in papers:
        doi = paper.get("doi", "")
        sim = similarity_scores.get(doi, 0.5)
        pr = pagerank_scores.get(doi, 0.5)
        combined = SIM_WEIGHT * sim + PR_WEIGHT * pr
        ranked.append({
            "doi": doi,
            "title": paper.get("title", ""),
            "abstract": (paper.get("abstract") or "")[:500],
            "year": paper.get("year"),
            "similarity_score": round(sim, 4),
            "pagerank_score": round(pr, 4),
            "combined_score": round(combined, 4),
        })

    ranked.sort(key=lambda x: x["combined_score"], reverse=True)

    if registry.log_service:
        await registry.log_service.log_agent_trace(
            project_id=project_id,
            agent_name="PlannerAgent",
            event_type="tool_call",
            details={"tool": "get_ranked_papers", "paper_count": len(ranked)},
        )

    return {"papers": ranked}


# ------------------------------------------------------------------
# T040 – generate_outline
# ------------------------------------------------------------------

async def generate_outline(
    style: str = "thematic",
    tool_context: ToolContext = None,  # type: ignore[assignment]
) -> dict[str, Any]:
    """Generate a structured literature review outline from the project's
    ranked papers and research questions.

    Uses the LLM to create thematic or chronological sections, each with
    assigned papers and descriptive summaries.  The result is saved to
    ``projects/{project_id}/outlines/outline.json``.

    Args:
        style: Outline style — one of 'thematic', 'chronological', or
               'methodological'.  Defaults to 'thematic'.

    Returns:
        A dict with keys: sections (list of section dicts), narrative_arc,
        style, and saved_path.
    """
    if tool_context is None:
        return {"error": "ToolContext is required."}

    project_id: str = tool_context.state.get("project_id", "")
    if not project_id:
        return {"error": "No project_id found in session state."}

    neo4j = registry.neo4j
    llm = registry.llm
    settings = get_settings()

    # Gather inputs
    questions = await neo4j.get_research_questions(project_id)
    question_texts = [q.get("text", "") for q in questions]

    # Get ranked papers (re-use logic inline for the LLM prompt)
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

    prompt = f"""You are an expert academic literature review planner.

Given the following research questions and collected papers, generate a structured
outline for a literature review using a **{style}** organisation style.

## Research Questions
{questions_block}

## Available Papers (ranked by relevance)
{papers_block}

## Instructions
1. Create 3-6 coherent sections that cover the research questions.
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

    # Persist to disk
    project_dir = Path(settings.projects_dir) / project_id / "outlines"
    project_dir.mkdir(parents=True, exist_ok=True)
    outline_path = project_dir / "outline.json"
    outline_path.write_text(json.dumps(outline_data, indent=2, ensure_ascii=False))

    # Store outline in session state for downstream agents
    tool_context.state["outline"] = outline_data

    # Log trace
    if registry.log_service:
        section_count = len(outline_data.get("sections", []))
        await registry.log_service.log_agent_trace(
            project_id=project_id,
            agent_name="PlannerAgent",
            event_type="tool_call",
            token_count=response.usage.total_tokens,
            details={
                "tool": "generate_outline",
                "style": style,
                "section_count": section_count,
            },
        )

    return {
        "sections": outline_data.get("sections", []),
        "narrative_arc": outline_data.get("narrative_arc", ""),
        "style": style,
        "saved_path": str(outline_path),
    }
