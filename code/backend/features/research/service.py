"""Research domain service — pure business logic, no ADK or FastAPI deps.

Functions in this module are the single source of truth for:
  - research-question management (CRUD + embedding)
  - top-author / top-venue analytics
  - OpenAlex search-by-author / search-by-venue
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from core.clients.openalex_client import OpenAlexService
    from core.db.neo4j_service import Neo4jService
    from core.llm.service import LLMService
    from features.embedding.providers.base import EmbeddingProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Research question management
# ---------------------------------------------------------------------------


async def add_research_question(
    project_id: str,
    question_text: str,
    neo4j: Neo4jService,
    embedding_provider: EmbeddingProvider,
) -> dict[str, Any]:
    """Generate a UUID, embed the text, and persist a new research question.

    Returns:
        ``{status, question_id, text, project_id}``
    """
    embedding = await embedding_provider.embed_query(query=question_text)
    question_id = str(uuid.uuid4())

    result = await neo4j.create_research_question(
        question_id=question_id,
        text=question_text,
        embedding=embedding,
        project_id=project_id,
    )

    return {
        "status": "created",
        "question_id": result.get("question_id", question_id),
        "text": result.get("text", question_text),
        "project_id": project_id,
    }


async def list_research_questions(
    project_id: str,
    neo4j: Neo4jService,
) -> dict[str, Any]:
    """Return all research questions for a project.

    Returns:
        ``{questions: [{question_id, text}, ...], total: int}``
    """
    questions = await neo4j.get_research_questions(project_id)
    return {
        "questions": [
            {"question_id": q.get("question_id"), "text": q.get("text")}
            for q in questions
        ],
        "total": len(questions),
    }


async def decompose_query(
    project_id: str,
    topic: str,
    num_questions: int = 4,
    auto_save: bool = False,
    llm: LLMService | None = None,
    neo4j: Neo4jService | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    """Decompose a high-level research topic into 3-5 domain-specific sub-questions.

    Uses Gemini LLM to generate granular, researchable questions covering methodologies,
    comparative benchmarks, architectures, and limitations.

    Args:
        project_id: Project UUID.
        topic: High-level research question or topic prompt.
        num_questions: Target number of sub-questions (3-5).
        auto_save: If True, automatically embeds and saves the questions to the project.
        llm: Injected LLMService instance.
        neo4j: Injected Neo4jService instance.
        embedding_provider: Injected EmbeddingProvider for auto-saving.

    Returns:
        Dict with keys: ``project_id``, ``topic``, ``sub_questions``, ``saved_questions``, ``total``.
    """
    from agents._service_registry import ServiceRegistry
    actual_llm = llm or ServiceRegistry.llm
    actual_neo4j = neo4j or ServiceRegistry.neo4j
    actual_emb = embedding_provider or ServiceRegistry.embedding_provider

    target_count = max(3, min(5, num_questions))
    prompt = f"""You are an expert academic research advisor. Decompose the following high-level research topic into {target_count} distinct, precise, and domain-specific academic sub-questions suitable for a comprehensive literature review.

High-Level Research Topic:
"{topic}"

Requirements for each sub-question:
1. Focus on specific technical facets (e.g., algorithmic architectures, comparative empirical performance, benchmark datasets, limitations/trade-offs).
2. Phrased clearly as an academic research question ending with a question mark.
3. Mutually non-redundant and collectively comprehensive.

Return a JSON object matching this exact schema:
{{
  "sub_questions": [
    "Sub-question 1?",
    "Sub-question 2?",
    "Sub-question 3?",
    "Sub-question 4?"
  ]
}}
"""
    questions: list[str] = []
    if actual_llm:
        try:
            from core.llm.models import CompletionRequest
            req = CompletionRequest(
                prompt=prompt,
                system_instruction="You are an expert academic research advisor. Return valid JSON only.",
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
            data = json.loads(raw)
            if isinstance(data, dict) and "sub_questions" in data:
                questions = [str(q).strip() for q in data["sub_questions"] if str(q).strip()]
            elif isinstance(data, list):
                questions = [str(q).strip() for q in data if str(q).strip()]
        except Exception as exc:
            logger.warning("LLM query decomposition failed (%s); using heuristic questions", exc)

    if not questions:
        clean_topic = topic.rstrip(".?")
        questions = [
            f"What state-of-the-art methodologies and architectures are used for {clean_topic}?",
            f"How do comparative empirical benchmarks evaluate performance in {clean_topic}?",
            f"What are the primary computational trade-offs and limitations of current approaches to {clean_topic}?",
            f"What emerging research directions and unresolved challenges exist in {clean_topic}?",
        ][:target_count]

    saved_questions: list[dict[str, Any]] = []
    if auto_save and actual_neo4j and actual_emb:
        for q_text in questions:
            saved = await add_research_question(
                project_id=project_id,
                question_text=q_text,
                neo4j=actual_neo4j,
                embedding_provider=actual_emb,
            )
            saved_questions.append(saved)

    return {
        "project_id": project_id,
        "topic": topic,
        "sub_questions": questions,
        "saved_questions": saved_questions,
        "total": len(questions),
    }


# ---------------------------------------------------------------------------
# Author / venue analytics
# ---------------------------------------------------------------------------


async def get_top_authors(
    project_id: str,
    limit: int,
    neo4j: Neo4jService,
) -> dict[str, Any]:
    """Return the most-frequent authors across papers in the project.

    Returns:
        ``{authors: [{name, openalex_id, paper_count}, ...], total: int}``
    """
    query = """
    MATCH (pr:Project {project_id: $project_id})-[:HAS_PAPER]->(p:Paper)
    MATCH (a:Author)-[:AUTHORED]->(p)
    RETURN a.name AS name, a.openalex_id AS openalex_id, count(p) AS paper_count
    ORDER BY paper_count DESC
    LIMIT $limit
    """
    records = await neo4j.execute_read(
        query,
        {"project_id": project_id, "limit": limit},
    )
    authors = [
        {
            "name": str(r["name"]),
            "openalex_id": r.get("openalex_id"),
            "paper_count": int(r.get("paper_count", 0)),
        }
        for r in records
        if r.get("name")
    ]
    return {"authors": authors, "total": len(authors)}


async def get_top_venues(
    project_id: str,
    limit: int,
    neo4j: Neo4jService,
) -> dict[str, Any]:
    """Return the most-frequent venues across papers in the project.

    Returns:
        ``{venues: [{name, openalex_id, paper_count}, ...], total: int}``
    """
    query = """
    MATCH (pr:Project {project_id: $project_id})-[:HAS_PAPER]->(p:Paper)-[:PUBLISHED_IN]->(v:Venue)
    RETURN v.name AS name, v.openalex_id AS openalex_id, count(p) AS paper_count
    ORDER BY paper_count DESC
    LIMIT $limit
    """
    records = await neo4j.execute_read(
        query,
        {"project_id": project_id, "limit": limit},
    )
    venues = [
        {
            "name": str(r["name"]),
            "openalex_id": r.get("openalex_id"),
            "paper_count": int(r.get("paper_count", 0)),
        }
        for r in records
        if r.get("name")
    ]
    return {"venues": venues, "total": len(venues)}


# ---------------------------------------------------------------------------
# OpenAlex search helpers
# ---------------------------------------------------------------------------


async def search_by_author(
    author_name: str,
    max_results: int,
    openalex: OpenAlexService,
) -> dict[str, Any]:
    """Search OpenAlex for papers by a specific author name.

    Returns:
        ``{papers: [{doi, title, year, cited_by_count, authors}, ...], total_returned: int}``
    """
    data = await openalex._request(
        "GET",
        "/works",
        params={
            "filter": f"authorships.author.display_name.search:{author_name}",
            "per_page": min(max_results, 25),
            "select": "doi,title,publication_year,cited_by_count,authorships",
        },
    )
    results: list[dict[str, object]] = data.get("results") or []  # type: ignore[assignment]
    papers: list[dict[str, object]] = []
    for work in results:
        doi = work.get("doi")
        if doi is None:
            continue
        doi_str = str(doi).replace("https://doi.org/", "")
        authorships: list[dict[str, object]] = work.get("authorships") or []  # type: ignore[assignment]
        author_names: list[str] = []
        for auth in authorships:
            author_info: dict[str, object] = auth.get("author", {})  # type: ignore[assignment]
            name = author_info.get("display_name")
            if name is not None:
                author_names.append(str(name))
        papers.append({
            "doi": doi_str,
            "title": str(work.get("title", "")),
            "year": work.get("publication_year"),
            "cited_by_count": int(work.get("cited_by_count") or 0),  # type: ignore[arg-type]
            "authors": author_names[:5],
        })
    return {"papers": papers, "total_returned": len(papers)}


async def search_by_venue(
    venue_name: str,
    max_results: int,
    openalex: OpenAlexService,
) -> dict[str, Any]:
    """Search OpenAlex for papers published in a specific venue.

    Returns:
        ``{papers: [{doi, title, year, cited_by_count, authors}, ...], total_returned: int}``
    """
    data = await openalex._request(
        "GET",
        "/works",
        params={
            "filter": f"primary_location.source.display_name.search:{venue_name}",
            "per_page": min(max_results, 25),
            "select": "doi,title,publication_year,cited_by_count,authorships",
            "sort": "cited_by_count:desc",
        },
    )
    results: list[dict[str, object]] = data.get("results") or []  # type: ignore[assignment]
    papers: list[dict[str, object]] = []
    for work in results:
        doi = work.get("doi")
        if doi is None:
            continue
        doi_str = str(doi).replace("https://doi.org/", "")
        authorships: list[dict[str, object]] = work.get("authorships") or []  # type: ignore[assignment]
        author_names: list[str] = []
        for auth in authorships:
            author_info: dict[str, object] = auth.get("author", {})  # type: ignore[assignment]
            name = author_info.get("display_name")
            if name is not None:
                author_names.append(str(name))
        papers.append({
            "doi": doi_str,
            "title": str(work.get("title", "")),
            "year": work.get("publication_year"),
            "cited_by_count": int(work.get("cited_by_count") or 0),  # type: ignore[arg-type]
            "authors": author_names[:5],
        })
    return {"papers": papers, "total_returned": len(papers)}
