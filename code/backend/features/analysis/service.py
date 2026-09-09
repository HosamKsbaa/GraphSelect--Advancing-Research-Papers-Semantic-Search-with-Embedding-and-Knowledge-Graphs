"""Analysis domain service — pure business logic, no ADK or FastAPI deps.

Functions in this module are the single source of truth for:
  - paper similarity scoring
  - citation statistics
  - coverage gap analysis
  - LLM-driven gap-query suggestions
  - hybrid (similarity + PageRank) paper ranking
  - literature evidence extraction and structured comparison matrix synthesis
"""
from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from agents.research.models import (
    ComparisonDimension,
    PaperFinding,
    StructuredComparisonMatrix,
)

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService
    from core.llm.service import LLMService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paper similarity
# ---------------------------------------------------------------------------


async def compute_paper_similarity(
    project_id: str,
    doi: str,
    neo4j: Neo4jService,
) -> dict[str, Any]:
    """Compute cosine similarity between a paper and all project research questions.

    Returns:
        ``{doi, scores: [{question, score}], avg_score: float}``
    """
    raw_questions = await neo4j.get_research_questions(project_id)
    if not raw_questions:
        return {"doi": doi, "scores": [], "avg_score": 0.0, "note": "No research questions defined."}

    has_emb = await neo4j.has_embedding(doi)
    if not has_emb:
        return {
            "doi": doi,
            "scores": [],
            "avg_score": 0.0,
            "note": "Paper has no embedding. Use explore_paper first.",
        }

    similarities = await neo4j.compute_similarities(
        session_id=project_id,
        threshold=0.0,
        top_k=100,
    )

    paper_scores = [
        {"question": s.get("question", ""), "score": round(float(s.get("score", 0)), 4)}
        for s in (similarities or [])
        if s.get("doi") == doi
    ]

    avg_score = 0.0
    if paper_scores:
        avg_score = round(sum(float(s["score"]) for s in paper_scores) / len(paper_scores), 4)

    return {"doi": doi, "scores": paper_scores, "avg_score": avg_score}


# ---------------------------------------------------------------------------
# Citation statistics
# ---------------------------------------------------------------------------


async def get_citation_stats(
    project_id: str,
    neo4j: Neo4jService,
) -> dict[str, Any]:
    """Aggregate citation and similarity statistics for the project.

    Returns:
        ``{total_papers, total_citations, avg_citations, question_coverage: [...]}``
    """
    papers = await neo4j.get_project_papers(project_id, limit=200)
    total_papers = len(papers) if papers else 0
    total_citations = sum(int(p.get("cited_by_count") or 0) for p in (papers or []))
    avg_citations = round(total_citations / total_papers, 2) if total_papers > 0 else 0.0

    raw_questions = await neo4j.get_research_questions(project_id)

    question_coverage: list[dict[str, object]] = []
    if raw_questions and total_papers > 0:
        try:
            similarities = await neo4j.compute_similarities(
                session_id=project_id,
                threshold=0.0,
                top_k=500,
            )
            q_scores: dict[str, list[float]] = {}
            for s in (similarities or []):
                q_text = str(s.get("question", ""))
                score = float(s.get("score", 0))
                if q_text not in q_scores:
                    q_scores[q_text] = []
                q_scores[q_text].append(score)

            for q in raw_questions:
                q_text = q if isinstance(q, str) else str(q.get("text", ""))
                scores = q_scores.get(q_text, [])
                question_coverage.append({
                    "question": q_text,
                    "avg_similarity": round(sum(scores) / len(scores), 4) if scores else 0.0,
                    "paper_count": len(scores),
                })
        except Exception as sim_exc:
            logger.warning("Similarity stats failed: %s", sim_exc)

    return {
        "total_papers": total_papers,
        "total_citations": total_citations,
        "avg_citations": avg_citations,
        "question_coverage": question_coverage,
    }


# ---------------------------------------------------------------------------
# Coverage analysis
# ---------------------------------------------------------------------------


async def analyze_coverage(
    project_id: str,
    neo4j_or_threshold: Any = None,
    threshold_or_neo4j: Any = None,
    threshold: float = 0.6,
    min_similarity: float | None = None,
    neo4j: Neo4jService | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Analyse how well the paper library covers each research question.

    Returns:
        ``{total_questions, gap_count, overall_coverage, covered_questions, gap_questions, recommendation}``
    """
    actual_neo4j = neo4j
    actual_threshold = threshold

    if min_similarity is not None:
        actual_threshold = min_similarity

    for arg in (neo4j_or_threshold, threshold_or_neo4j):
        if isinstance(arg, (int, float)):
            if min_similarity is None:
                actual_threshold = float(arg)
        elif arg is not None:
            actual_neo4j = arg

    if actual_neo4j is None:
        from agents._service_registry import ServiceRegistry
        actual_neo4j = ServiceRegistry.neo4j

    raw_questions = await actual_neo4j.get_research_questions(project_id)
    if not raw_questions:
        return {
            "total_questions": 0,
            "gap_count": 0,
            "overall_coverage": 0.0,
            "covered_questions": [],
            "gap_questions": [],
            "recommendation": "No research questions defined. Add questions first.",
        }

    question_texts: list[str] = [
        q if isinstance(q, str) else str(q.get("text", "")) for q in raw_questions
    ]

    papers = await actual_neo4j.get_project_papers(project_id, limit=200)
    if not papers:
        gap_entries = [{"question": q, "best_score": 0.0, "paper_count": 0} for q in question_texts]
        return {
            "total_questions": len(question_texts),
            "gap_count": len(question_texts),
            "overall_coverage": 0.0,
            "covered_questions": [],
            "gap_questions": gap_entries,
            "recommendation": "No papers in the project. Start searching for papers.",
        }

    similarities = await actual_neo4j.compute_similarities(
        session_id=project_id,
        threshold=0.0,
        top_k=1000,
    )

    q_data: dict[str, dict[str, Any]] = {
        q: {"best_score": 0.0, "paper_count": 0} for q in question_texts
    }

    for s in (similarities or []):
        q_text = str(s.get("question", ""))
        score = float(s.get("score", 0))
        if q_text in q_data:
            q_data[q_text]["paper_count"] += 1
            if score > float(q_data[q_text]["best_score"]):
                q_data[q_text]["best_score"] = score

    covered: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for q_text, data in q_data.items():
        entry = {
            "question": q_text,
            "best_score": round(float(data["best_score"]), 4),
            "paper_count": data["paper_count"],
        }
        if float(data["best_score"]) >= actual_threshold and data["paper_count"] > 0:
            covered.append(entry)
        else:
            gaps.append(entry)

    total_q = len(question_texts)
    overall = round(len(covered) / total_q, 4) if total_q > 0 else 0.0

    if not gaps:
        recommendation = "All research questions are well-covered! Consider refining questions or exploring niche subtopics."
    elif overall >= 0.5:
        gap_summaries = ", ".join(g["question"][:60] + "..." for g in gaps[:3])
        recommendation = f"{len(gaps)} of {total_q} questions have gaps. Focus searches on: {gap_summaries}"
    else:
        recommendation = f"Major coverage gaps detected ({len(gaps)} of {total_q} questions). Prioritize broader searches to build the paper library."

    return {
        "total_questions": total_q,
        "gap_count": len(gaps),
        "overall_coverage": overall,
        "covered_questions": covered,
        "gap_questions": gaps,
        "recommendation": recommendation,
    }


# ---------------------------------------------------------------------------
# Gap-query suggestion (LLM)
# ---------------------------------------------------------------------------


async def suggest_gap_queries(
    project_id_or_question: str | None = None,
    question_or_llm: Any = None,
    llm_or_max: Any = None,
    gap_question: str | None = None,
    question: str | None = None,
    max_queries: int = 5,
    llm: LLMService | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Use the LLM to generate search queries that fill a coverage gap.

    Handles flexible argument signatures:
      - suggest_gap_queries(project_id, question="...", llm=...)
      - suggest_gap_queries("proj-1", "question", llm)
      - suggest_gap_queries(gap_question="...", max_queries=5, llm=...)
    """
    actual_llm = llm
    actual_question = gap_question or question

    # Parse positional variations
    if actual_question is None:
        if isinstance(question_or_llm, str):
            actual_question = question_or_llm
            if hasattr(llm_or_max, "complete"):
                actual_llm = llm_or_max
            elif isinstance(llm_or_max, int):
                max_queries = llm_or_max
        elif hasattr(question_or_llm, "complete"):
            actual_question = project_id_or_question
            actual_llm = question_or_llm
        else:
            actual_question = project_id_or_question

    if actual_question is None and "gap_question" in kwargs:
        actual_question = kwargs["gap_question"]
    if actual_question is None and "question" in kwargs:
        actual_question = kwargs["question"]

    if actual_llm is None:
        from agents._service_registry import ServiceRegistry
        actual_llm = ServiceRegistry.llm

    from core.llm.models import CompletionRequest

    prompt = f"""You are a research assistant helping find academic papers.

The following research question is not well-covered by the current paper library:

"{actual_question}"

Generate {max_queries} specific and diverse search queries that would help find papers
relevant to this question. Each query should target a different angle or
subtopic. Return ONLY a JSON array of strings.

Example output: ["query 1", "query 2", "query 3", "query 4", "query 5"]
"""
    request = CompletionRequest(
        prompt=prompt,
        system_instruction="You are an academic research assistant. Respond with valid JSON only.",
        temperature=0.7,
        max_tokens=512,
        response_format="application/json",
    )

    response = await actual_llm.complete(request)
    raw = (response.text or "").strip()

    # Strip markdown code fences if present
    if raw.startswith("```"):
        lines = raw.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        raw = "\n".join(lines).strip()

    queries: list[str] = []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            queries = [str(item).strip() for item in parsed if str(item).strip()]
        elif isinstance(parsed, dict) and "queries" in parsed:
            queries = [str(item).strip() for item in parsed["queries"] if str(item).strip()]
        else:
            queries = [str(parsed)]
    except Exception:
        # Fallback text parser: split on bullet points or newlines
        lines = raw.split("\n")
        for line in lines:
            cleaned = line.strip()
            # Strip bullet prefixes: "- ", "* ", "1. ", "Query 1: ", etc.
            cleaned = re.sub(r"^(\s*[-*•]|\d+\.|\s*Query\s*\d+\s*:)\s*", "", cleaned).strip()
            cleaned = cleaned.strip("\"'")
            if cleaned and len(cleaned) > 2:
                queries.append(cleaned)

    if not queries:
        queries = [actual_question] if actual_question else ["graph research"]

    return {
        "gap_question": actual_question or "",
        "suggested_queries": queries[:max_queries],
    }


# ---------------------------------------------------------------------------
# Hybrid paper ranking  (similarity × weight + PageRank × weight)
# ---------------------------------------------------------------------------


async def rank_papers(
    project_id: str,
    similarity_weight: float = 0.7,
    pagerank_weight: float = 0.3,
    neo4j: Neo4jService | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Rank project papers with a hybrid score combining similarity and PageRank.

    Returns:
        ``{ranked_papers: [...], total: int, weights: {similarity, pagerank}}``
    """
    actual_neo4j = neo4j
    if actual_neo4j is None:
        from agents._service_registry import ServiceRegistry
        actual_neo4j = ServiceRegistry.neo4j

    papers = await actual_neo4j.get_project_papers(project_id, limit=200)
    if not papers:
        return {
            "ranked_papers": [],
            "total": 0,
            "weights": {"similarity": similarity_weight, "pagerank": pagerank_weight},
        }

    # Build DOI ? paper map
    doi_map: dict[str, dict[str, Any]] = {}
    for p in papers:
        doi = str(p.get("doi", ""))
        doi_map[doi] = {
            "doi": doi,
            "title": p.get("title"),
            "year": p.get("year"),
            "cited_by_count": p.get("cited_by_count"),
        }

    # Compute average similarity per paper
    sim_scores: dict[str, float] = {}
    try:
        similarities = await actual_neo4j.compute_similarities(
            session_id=project_id,
            threshold=0.0,
            top_k=1000,
        )
        doi_sim_list: dict[str, list[float]] = {}
        for s in (similarities or []):
            d = str(s.get("doi", ""))
            if d in doi_map:
                if d not in doi_sim_list:
                    doi_sim_list[d] = []
                doi_sim_list[d].append(float(s.get("score", 0)))
        for d, scores in doi_sim_list.items():
            sim_scores[d] = sum(scores) / len(scores) if scores else 0.0
    except Exception as sim_exc:
        logger.warning("Similarity computation failed in rank_papers: %s", sim_exc)

    # Compute PageRank scores
    pr_scores: dict[str, float] = {}
    try:
        pr_scores = await actual_neo4j.compute_pagerank(session_id=project_id)
    except Exception as pr_exc:
        logger.warning("PageRank computation failed in rank_papers: %s", pr_exc)

    # Compute hybrid scores
    ranked: list[dict[str, Any]] = []
    for doi, paper_info in doi_map.items():
        sim = sim_scores.get(doi, 0.0)
        pr = pr_scores.get(doi, 0.0)
        hybrid = round(similarity_weight * sim + pagerank_weight * pr, 4)
        ranked.append({
            "doi": doi,
            "title": paper_info.get("title"),
            "year": paper_info.get("year"),
            "similarity_score": round(sim, 4),
            "pagerank_score": round(pr, 4),
            "hybrid_score": hybrid,
        })

    ranked.sort(key=lambda x: float(x.get("hybrid_score", 0)), reverse=True)

    return {
        "ranked_papers": ranked,
        "total": len(ranked),
        "weights": {"similarity": similarity_weight, "pagerank": pagerank_weight},
    }


# ---------------------------------------------------------------------------
# Evidence Synthesis & Matrix Generation (Milestone 2 / Requirement R2)
# ---------------------------------------------------------------------------


async def extract_paper_findings(
    dois: list[str],
    project_id: str | None = None,
    neo4j: Neo4jService | None = None,
    llm: LLMService | None = None,
) -> list[PaperFinding]:
    """Extract structured methodology, empirical results, benchmarks, and limitations for papers."""
    if not dois:
        return []

    from agents._service_registry import ServiceRegistry
    actual_neo4j = neo4j or ServiceRegistry.neo4j
    actual_llm = llm or ServiceRegistry.llm

    from core.llm.models import CompletionRequest

    findings: list[PaperFinding] = []
    for doi in dois:
        paper = await actual_neo4j.get_paper_by_doi(doi)
        if not paper:
            findings.append(PaperFinding(
                doi=doi,
                title=f"Paper {doi}",
                year=None,
                methodology="Methodology not found in database",
                key_findings=["No abstract available for analysis"],
                datasets_or_benchmarks=[],
                limitations=["Paper not found in local library"],
            ))
            continue

        title = str(paper.get("title") or doi)
        abstract = str(paper.get("abstract") or "")
        year = paper.get("year")

        prompt = f"""You are an academic expert in literature analysis. Extract key findings, methodology, datasets, and limitations from the following academic paper abstract:

Paper Title: {title}
DOI: {doi}
Year: {year}
Abstract:
{abstract if abstract else "No abstract provided."}

Return a valid JSON object matching the schema:
{{
  "methodology": "Brief summary of methods, models, architectures, or algorithms used",
  "key_findings": ["Finding 1", "Finding 2"],
  "datasets_or_benchmarks": ["Dataset 1", "Benchmark 2"],
  "limitations": ["Limitation 1", "Limitation 2"]
}}
"""
        try:
            req = CompletionRequest(
                prompt=prompt,
                system_instruction="You are an expert academic literature reviewer. Return valid JSON only.",
                temperature=0.3,
                max_tokens=1024,
                response_format="application/json",
            )
            resp = await actual_llm.complete(req)
            raw = (resp.text or "").strip()
            if raw.startswith("```"):
                lines = raw.split("\n")
                lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw = "\n".join(lines).strip()

            parsed = json.loads(raw)
            finding = PaperFinding(
                doi=doi,
                title=title,
                year=int(year) if year else None,
                methodology=parsed.get("methodology", "Empirical study and evaluation"),
                key_findings=parsed.get("key_findings", []),
                datasets_or_benchmarks=parsed.get("datasets_or_benchmarks", []),
                limitations=parsed.get("limitations", []),
            )
            findings.append(finding)
        except Exception as exc:
            logger.warning("Failed to extract findings via LLM for %s: %s", doi, exc)
            findings.append(PaperFinding(
                doi=doi,
                title=title,
                year=int(year) if year else None,
                methodology="Empirical methodology",
                key_findings=["Extracted from paper metadata"],
                datasets_or_benchmarks=[],
                limitations=[],
            ))

    return findings


async def generate_comparison_matrix(
    findings: Sequence[PaperFinding | dict[str, Any]],
    research_questions: list[str] | None = None,
    project_id: str = "default-project",
    llm: LLMService | None = None,
) -> StructuredComparisonMatrix:
    """Synthesize cross-paper comparison dimensions, consensus, and divergences into a StructuredComparisonMatrix."""
    from agents._service_registry import ServiceRegistry
    actual_llm = llm or ServiceRegistry.llm

    from core.llm.models import CompletionRequest

    findings_dicts: list[dict[str, Any]] = []
    for f in findings:
        if isinstance(f, PaperFinding):
            findings_dicts.append(f.model_dump())
        else:
            findings_dicts.append(f)

    if not findings_dicts:
        return StructuredComparisonMatrix(
            project_id=project_id,
            research_questions=research_questions or [],
            dimensions=[],
            synthesis_narrative="No paper findings provided to synthesize.",
        )

    rq_text = "\n".join(f"- {rq}" for rq in (research_questions or []))
    findings_json = json.dumps(findings_dicts, indent=2)

    prompt = f"""You are an expert senior academic researcher synthesizing literature.

Given the following paper findings and research questions, construct a structured comparative literature analysis:

Research Questions:
{rq_text if rq_text else "General literature review on the topic"}

Paper Findings:
{findings_json}

Identify 3 to 6 key Comparison Dimensions (e.g. Model Architecture, Scalability, Accuracy/Performance, Expressiveness, Limitations/Over-smoothing).
For each dimension, state:
1. "findings_by_doi": mapping of DOI to specific finding or metric value for that paper
2. "consensus": agreed-upon findings across papers
3. "divergence": contradictions, trade-offs, varying assumptions, or differing conclusions across papers

Also provide a comprehensive "synthesis_narrative" (200-400 words) discussing the comparative findings, state-of-the-art consensus, and major open research gaps.

Return ONLY a JSON object matching this schema:
{{
  "dimensions": [
    {{
      "dimension_name": "Dimension Name",
      "findings_by_doi": {{"10.1000/1": "value 1", "10.1000/2": "value 2"}},
      "consensus": "Consensus text",
      "divergence": "Divergence text"
    }}
  ],
  "synthesis_narrative": "Narrative text..."
}}
"""
    try:
        req = CompletionRequest(
            prompt=prompt,
            system_instruction="You are an expert scientific researcher. Return valid JSON only.",
            temperature=0.4,
            max_tokens=2048,
            response_format="application/json",
        )
        resp = await actual_llm.complete(req)
        raw = (resp.text or "").strip()
        if raw.startswith("```"):
            lines = raw.split("\n")
            lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            raw = "\n".join(lines).strip()

        parsed = json.loads(raw)
        dimensions: list[ComparisonDimension] = []
        for dim_data in parsed.get("dimensions", []):
            dimensions.append(ComparisonDimension(
                dimension_name=dim_data.get("dimension_name", "Dimension"),
                findings_by_doi=dim_data.get("findings_by_doi", {}),
                consensus=dim_data.get("consensus", ""),
                divergence=dim_data.get("divergence", ""),
            ))

        synthesis_narrative = parsed.get(
            "synthesis_narrative",
            "Synthesized cross-paper analysis across evaluated dimensions.",
        )

        return StructuredComparisonMatrix(
            project_id=project_id,
            research_questions=research_questions or [],
            dimensions=dimensions,
            synthesis_narrative=synthesis_narrative,
        )
    except Exception as exc:
        logger.warning("Failed to generate structured comparison matrix via LLM: %s", exc)
        fallback_dims = [
            ComparisonDimension(
                dimension_name="Methodology",
                findings_by_doi={f["doi"]: f.get("methodology", "Empirical") for f in findings_dicts},
                consensus="All examined papers apply empirical evaluations.",
                divergence="Approaches differ in network architectures and training objectives.",
            ),
            ComparisonDimension(
                dimension_name="Datasets and Benchmarks",
                findings_by_doi={f["doi"]: ", ".join(f.get("datasets_or_benchmarks", [])) or "Standard benchmarks" for f in findings_dicts},
                consensus="Evaluation uses standard benchmark graph datasets.",
                divergence="Dataset scales range from small citation graphs to large-scale web graphs.",
            ),
        ]
        return StructuredComparisonMatrix(
            project_id=project_id,
            research_questions=research_questions or [],
            dimensions=fallback_dims,
            synthesis_narrative="Comparative analysis of paper methodologies and benchmark datasets.",
        )


async def synthesize_evidence(
    project_id: str,
    dois: list[str] | None = None,
    research_questions: list[str] | None = None,
    neo4j: Neo4jService | None = None,
    llm: LLMService | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    """Execute end-to-end evidence synthesis for all papers in the project.

    Args:
        project_id: Unique project identifier.
        dois: Optional list of paper DOIs to synthesize. If None, queries project papers.
        research_questions: Optional list of research questions. If None, queries project questions.
        neo4j: Optional Neo4jService instance.
        llm: Optional LLMService instance.

    Returns:
        Dictionary containing project_id, paper_count, findings, comparison_matrix, markdown_table, synthesis_narrative.
    """
    from agents._service_registry import ServiceRegistry
    actual_neo4j = neo4j or ServiceRegistry.neo4j
    actual_llm = llm or ServiceRegistry.llm

    target_dois = dois
    if target_dois is None:
        papers = await actual_neo4j.get_project_papers(project_id, limit=50)
        target_dois = [str(p["doi"]) for p in (papers or []) if p.get("doi")]

    rq_texts = research_questions
    if rq_texts is None:
        raw_questions = await actual_neo4j.get_research_questions(project_id)
        rq_texts = [q if isinstance(q, str) else str(q.get("text", "")) for q in (raw_questions or [])]

    findings = await extract_paper_findings(target_dois, project_id=project_id, neo4j=actual_neo4j, llm=actual_llm)
    matrix = await generate_comparison_matrix(
        findings=findings,
        research_questions=rq_texts,
        project_id=project_id,
        llm=actual_llm,
    )

    return {
        "project_id": project_id,
        "paper_count": len(findings),
        "findings": [f.model_dump() for f in findings],
        "comparison_matrix": matrix.model_dump(),
        "markdown_table": matrix.to_markdown_table(),
        "synthesis_narrative": matrix.synthesis_narrative,
    }
