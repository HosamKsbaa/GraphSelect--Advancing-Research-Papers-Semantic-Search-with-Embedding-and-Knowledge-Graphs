"""Analysis and evidence synthesis tools for GapFinderAgent and EvidenceSynthesizerAgent.

These tools compute similarity scores, analyze coverage gaps, generate
search queries for uncovered areas, produce hybrid paper rankings, extract
paper methodologies/findings, and construct structured comparison matrices.
"""
from __future__ import annotations

import logging
from typing import Any

from google.adk.tools.tool_context import ToolContext

from agents._service_registry import ServiceRegistry
from agents.research.models import (
    ComparisonDimension,
    PaperFinding,
    StructuredComparisonMatrix,
)

logger = logging.getLogger(__name__)


def _resolve_context(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    direct_context: ToolContext | None = None,
) -> ToolContext | None:
    """Resolve ToolContext from direct arg, kwargs, or positional arguments."""
    if direct_context is not None:
        return direct_context
    if "tool_context" in kwargs and kwargs["tool_context"] is not None:
        return kwargs["tool_context"]
    if "context" in kwargs and kwargs["context"] is not None:
        return kwargs["context"]
    if args:
        if hasattr(args[0], "state") or isinstance(args[0], ToolContext):
            return args[0]
        if len(args) > 1 and (hasattr(args[1], "state") or isinstance(args[1], ToolContext)):
            return args[1]
    return None


def _get_project_id(tool_context: ToolContext | None) -> str | None:
    """Extract project_id from the ADK ToolContext state."""
    if tool_context is None:
        return None
    state = getattr(tool_context, "state", None)
    if state is None:
        return None
    if isinstance(state, dict):
        return state.get("project_id")
    if hasattr(state, "get"):
        return state.get("project_id")
    return getattr(state, "project_id", None)


async def compute_similarity(
    *args: Any,
    doi: str = "",
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Compute cosine similarity between a paper and all project research questions."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_doi = doi if doi else (kwargs.get("doi") or "")
    if not actual_doi and args:
        for a in args:
            if isinstance(a, str) and not hasattr(a, "state"):
                actual_doi = a
                break

    project_id = _get_project_id(ctx)
    if project_id is None:
        return {"error": "No project_id in session state.", "doi": actual_doi, "scores": [], "avg_score": 0.0}

    try:
        from features.analysis.service import compute_paper_similarity

        return await compute_paper_similarity(
            project_id=project_id, doi=actual_doi, neo4j=ServiceRegistry.neo4j,
        )
    except Exception as exc:
        logger.error("compute_similarity failed for %s: %s", actual_doi, exc)
        return {"error": str(exc), "doi": actual_doi, "scores": [], "avg_score": 0.0}


async def get_citation_stats(
    *args: Any,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Get aggregate citation and similarity statistics for the project."""
    ctx = _resolve_context(args, kwargs, tool_context)
    project_id = _get_project_id(ctx)
    if project_id is None:
        return {"error": "No project_id in session state."}

    try:
        from features.analysis.service import get_citation_stats as _get_citation_stats

        return await _get_citation_stats(project_id=project_id, neo4j=ServiceRegistry.neo4j)
    except Exception as exc:
        logger.error("get_citation_stats failed: %s", exc)
        return {"error": str(exc)}


async def analyze_coverage(
    *args: Any,
    threshold: float = 0.6,
    min_similarity: float | None = None,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Analyze how well the current paper library covers each research question."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_thresh = threshold
    if min_similarity is not None:
        actual_thresh = min_similarity
    elif "min_similarity" in kwargs and kwargs["min_similarity"] is not None:
        actual_thresh = float(kwargs["min_similarity"])
    elif "threshold" in kwargs and kwargs["threshold"] is not None:
        actual_thresh = float(kwargs["threshold"])
    elif args:
        for a in args:
            if isinstance(a, (int, float)):
                actual_thresh = float(a)
                break

    project_id = _get_project_id(ctx)
    if project_id is None:
        return {"error": "No project_id in session state."}

    try:
        from features.analysis.service import analyze_coverage as _analyze_coverage

        return await _analyze_coverage(
            project_id=project_id, threshold=float(actual_thresh), neo4j=ServiceRegistry.neo4j,
        )
    except Exception as exc:
        logger.error("analyze_coverage failed: %s", exc)
        return {"error": str(exc)}


async def suggest_gap_queries(
    *args: Any,
    gap_question: str = "",
    question: str | None = None,
    max_queries: int = 5,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Generate search queries to find papers that fill a coverage gap."""
    ctx = _resolve_context(args, kwargs, tool_context)
    target_q = gap_question or question or kwargs.get("gap_question") or kwargs.get("question") or ""
    if not target_q and args:
        for a in args:
            if isinstance(a, str) and not hasattr(a, "state"):
                target_q = a
                break

    actual_max = kwargs.get("max_queries", max_queries)
    if args:
        for a in args:
            if isinstance(a, int):
                actual_max = a
                break

    try:
        from features.analysis.service import suggest_gap_queries as _suggest_gap_queries

        return await _suggest_gap_queries(
            gap_question=target_q,
            max_queries=actual_max,
            llm=ServiceRegistry.llm,
        )
    except Exception as exc:
        logger.error("suggest_gap_queries failed: %s", exc)
        return {
            "error": str(exc),
            "gap_question": target_q,
            "suggested_queries": [],
        }


async def rank_papers(
    *args: Any,
    similarity_weight: float = 0.7,
    pagerank_weight: float = 0.3,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Rank project papers using a hybrid score combining similarity and PageRank."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_sim = kwargs.get("similarity_weight", similarity_weight)
    actual_pr = kwargs.get("pagerank_weight", pagerank_weight)

    project_id = _get_project_id(ctx)
    if project_id is None:
        return {"error": "No project_id in session state."}

    try:
        from features.analysis.service import rank_papers as _rank_papers

        return await _rank_papers(
            project_id=project_id,
            similarity_weight=float(actual_sim),
            pagerank_weight=float(actual_pr),
            neo4j=ServiceRegistry.neo4j,
        )
    except Exception as exc:
        logger.error("rank_papers failed: %s", exc)
        return {"error": str(exc)}


async def extract_paper_findings(
    *args: Any,
    dois: list[str] | None = None,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Extract structured methodology, empirical results, benchmarks, and limitations for papers."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_dois = dois if dois is not None else kwargs.get("dois")
    if actual_dois is None and args:
        for a in args:
            if isinstance(a, list):
                actual_dois = a
                break

    if actual_dois is None:
        actual_dois = []

    project_id = _get_project_id(ctx)

    try:
        from features.analysis.service import extract_paper_findings as _extract_findings

        findings = await _extract_findings(
            dois=actual_dois,
            project_id=project_id,
            neo4j=ServiceRegistry.neo4j,
            llm=ServiceRegistry.llm,
        )
        return {
            "total_extracted": len(findings),
            "findings": [f.model_dump() for f in findings],
        }
    except Exception as exc:
        logger.error("extract_paper_findings failed: %s", exc)
        return {"error": str(exc), "total_extracted": 0, "findings": []}


async def generate_comparison_matrix(
    *args: Any,
    findings: list[dict[str, Any]] | None = None,
    research_questions: list[str] | None = None,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Synthesize cross-paper comparison dimensions, consensus, and divergences into a structured comparison matrix."""
    ctx = _resolve_context(args, kwargs, tool_context)
    actual_findings = findings if findings is not None else kwargs.get("findings")
    if actual_findings is None and args:
        for a in args:
            if isinstance(a, list):
                actual_findings = a
                break

    if actual_findings is None:
        actual_findings = []

    actual_rqs = kwargs.get("research_questions", research_questions)
    project_id = _get_project_id(ctx) or "default-project"

    try:
        from features.analysis.service import generate_comparison_matrix as _gen_matrix

        if actual_rqs is None and project_id and ServiceRegistry.is_initialized():
            try:
                raw_qs = await ServiceRegistry.neo4j.get_research_questions(project_id)
                actual_rqs = [q if isinstance(q, str) else str(q.get("text", "")) for q in (raw_qs or [])]
            except Exception:
                actual_rqs = []

        matrix = await _gen_matrix(
            findings=actual_findings,
            research_questions=actual_rqs or [],
            project_id=project_id,
            llm=ServiceRegistry.llm,
        )

        matrix_dict = matrix.model_dump()

        if ctx is not None:
            state = getattr(ctx, "state", None)
            if state is not None:
                if isinstance(state, dict):
                    state["comparison_matrix"] = matrix_dict
                elif hasattr(state, "__setitem__"):
                    state["comparison_matrix"] = matrix_dict

        return {
            "project_id": project_id,
            "dimensions_count": len(matrix.dimensions),
            "matrix": matrix_dict,
            "markdown_table": matrix.to_markdown_table(),
            "synthesis_narrative": matrix.synthesis_narrative,
        }
    except Exception as exc:
        logger.error("generate_comparison_matrix failed: %s", exc)
        return {"error": str(exc)}


async def synthesize_evidence(
    *args: Any,
    tool_context: ToolContext | None = None,
    **kwargs: Any,
) -> dict[str, object]:
    """Execute end-to-end evidence synthesis for all papers in the active project."""
    ctx = _resolve_context(args, kwargs, tool_context)
    project_id = _get_project_id(ctx)
    if project_id is None:
        return {"error": "No project_id in session state. Select a project first."}

    try:
        from features.analysis.service import synthesize_evidence as _synth_evidence

        result = await _synth_evidence(
            project_id=project_id,
            neo4j=ServiceRegistry.neo4j,
            llm=ServiceRegistry.llm,
        )

        if ctx is not None:
            state = getattr(ctx, "state", None)
            if state is not None:
                if isinstance(state, dict):
                    state["comparison_matrix"] = result["comparison_matrix"]
                elif hasattr(state, "__setitem__"):
                    state["comparison_matrix"] = result["comparison_matrix"]

        return result
    except Exception as exc:
        logger.error("synthesize_evidence failed: %s", exc)
        return {"error": str(exc)}
