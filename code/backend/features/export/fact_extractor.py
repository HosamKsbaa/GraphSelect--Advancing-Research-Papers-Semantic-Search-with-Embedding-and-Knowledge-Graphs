"""Neo4j Epistemic Fact Extraction Service for Presentation Deck Generation.

Executes parameterized Cypher queries conforming to contracts/cypher_queries.md.
Adheres strictly to Constitution v2.2.1 (C7 static typing, C8 zero MySQL, C9 <=25 line functions).
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from features.export.presentation_models import (
    PresentationErrorCode,
    ProjectEpistemicFacts,
    ResearchQuestionFact,
    ScientometricFacts,
    SvplPathwayFact,
    SynthesisMatrixFact,
)

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService

logger = logging.getLogger(__name__)


METADATA_QUERY = (
    "MATCH (proj:Project {project_id: $project_id})\n"
    "OPTIONAL MATCH (rq:ResearchQuestion)\n"
    "WHERE (proj)-[:HAS_RESEARCH_QUESTION]->(rq) OR (rq)-[:BELONGS_TO]->(proj) "
    "OR rq.project_id = proj.project_id\n"
    "OPTIONAL MATCH (rq)<-[:ADDRESSES|EVALUATED_AGAINST|SYNTHESIZES]-(p:Paper)\n"
    "WITH proj, rq, count(DISTINCT p) AS paper_count\n"
    "ORDER BY coalesce(rq.order, 0) ASC, coalesce(rq.created_at, datetime()) ASC\n"
    "RETURN proj.project_id AS project_id, proj.name AS project_name, "
    "coalesce(proj.domain, 'Computer Science / Artificial Intelligence') AS domain, "
    "coalesce(proj.description, '') AS description, "
    "toString(proj.created_at) AS creation_date, "
    "coalesce(proj.current_stage, 'stage_4_synthesis') AS workflow_stage, "
    "collect(CASE WHEN rq IS NOT NULL THEN { "
    "rq_id: coalesce(rq.question_id, rq.rq_id, 'rq-unknown'), "
    "finer_text: coalesce(rq.finer_text, rq.text, 'Untitled RQ'), "
    "coverage_score: coalesce(rq.coverage_score, 0.0), "
    "status: CASE WHEN coalesce(rq.is_open_frontier, false) = true "
    "OR coalesce(rq.coverage_score, 0.0) < 0.70 THEN 'open_frontier' ELSE 'grounded' END, "
    "grounded_paper_count: coalesce(rq.grounded_paper_count, paper_count) "
    "} ELSE null END) AS research_questions"
)

SCIENTOMETRICS_QUERY = (
    "MATCH (proj:Project {project_id: $project_id})-[:HAS_PAPER|CONTAINS_PAPER]->(p:Paper)\n"
    "WITH proj, count(p) AS total_papers, "
    "coalesce(sum(coalesce(p.cited_by_count, p.citation_count, 0)), 0) AS total_citations\n"
    "OPTIONAL MATCH (proj)-[:HAS_PAPER|CONTAINS_PAPER]->(p:Paper)<-[:AUTHORED|AUTHORED_BY]-(a:Author)\n"
    "WITH proj, total_papers, total_citations, count(DISTINCT a) AS unique_authors\n"
    "CALL {\n"
    "  WITH proj\n"
    "  OPTIONAL MATCH (proj)-[:HAS_PAPER|CONTAINS_PAPER]->(p:Paper)\n"
    "  WHERE p.year IS NOT NULL AND p.year > 1990\n"
    "  WITH p.year AS pub_year, count(p) AS year_count\n"
    "  ORDER BY pub_year ASC\n"
    "  RETURN collect(CASE WHEN pub_year IS NOT NULL THEN {year: pub_year, count: year_count} ELSE null END) AS year_distribution\n"
    "}\n"
    "CALL {\n"
    "  WITH proj\n"
    "  OPTIONAL MATCH (proj)-[:HAS_PAPER|CONTAINS_PAPER]->(p:Paper)\n"
    "  OPTIONAL MATCH (p)-[:PUBLISHED_IN]->(v:Venue)\n"
    "  WITH coalesce(v.name, p.venue, '') AS venue_name, count(p) AS venue_count\n"
    "  WHERE trim(venue_name) <> ''\n"
    "  ORDER BY venue_count DESC LIMIT 8\n"
    "  RETURN collect({venue: venue_name, count: venue_count}) AS top_venues\n"
    "}\n"
    "CALL {\n"
    "  WITH proj\n"
    "  OPTIONAL MATCH (proj)-[:HAS_PAPER|CONTAINS_PAPER]->(p:Paper)<-[:AUTHORED|AUTHORED_BY]-(a:Author)\n"
    "  WHERE a.name IS NOT NULL AND trim(a.name) <> ''\n"
    "  WITH a.name AS author_name, count(p) AS author_papers\n"
    "  ORDER BY author_papers DESC LIMIT 8\n"
    "  RETURN collect({author: author_name, count: author_papers}) AS top_authors\n"
    "}\n"
    "RETURN total_papers, total_citations, unique_authors, year_distribution, top_venues, top_authors"
)


class PresentationFactExtractor:
    """Extracts deterministic ground-truth facts from Neo4j SSOT for presentation slides."""

    def __init__(self, neo4j: Neo4jService | Any) -> None:
        self.neo4j = neo4j

    @staticmethod
    def _get_metadata_query() -> str:
        """Construct parameterized Cypher Query 1 for project metadata and RQs."""
        return METADATA_QUERY

    @staticmethod
    def _build_project_meta(row: dict[str, Any]) -> dict[str, Any]:
        """Format raw project metadata dictionary from query row."""
        return {
            "project_id": row["project_id"],
            "project_name": row.get("project_name") or "Untitled Campaign",
            "domain": row.get("domain") or "General Research",
            "description": row.get("description") or "",
            "creation_date": str(row.get("creation_date") or ""),
            "workflow_stage": row.get("workflow_stage") or "stage_4_synthesis",
        }

    async def extract_project_metadata_and_rqs(
        self, project_id: str
    ) -> tuple[dict[str, Any], list[ResearchQuestionFact]]:
        """Execute Query 1: Extract project metadata and research questions."""
        records = await self.neo4j.execute_read(self._get_metadata_query(), {"project_id": project_id})
        if not records:
            msg = f"{PresentationErrorCode.PROJECT_NOT_FOUND.value}: Project '{project_id}' not found"
            raise ValueError(msg)
        meta = self._build_project_meta(records[0])
        raw_rqs = records[0].get("research_questions") or []
        return meta, self._parse_rq_records(raw_rqs)

    def _parse_rq_records(self, raw_rqs: list[dict[str, Any] | None]) -> list[ResearchQuestionFact]:
        """Convert raw query research question records into Pydantic models."""
        valid_rqs: list[ResearchQuestionFact] = []
        for r in raw_rqs:
            if not r:
                continue
            qid = str(r.get("rq_id") or "rq-unknown")
            text = str(r.get("finer_text") or "")
            cov = float(r.get("coverage_score") or 0.0)
            valid_rqs.append(
                ResearchQuestionFact(
                    question_id=qid,
                    rq_id=qid,
                    text=text,
                    finer_text=text,
                    coverage_score=max(0.0, min(1.0, cov)),
                    status=str(r.get("status") or "open_frontier"),
                    grounded_paper_count=int(r.get("grounded_paper_count") or 0),
                )
            )
        return valid_rqs

    @staticmethod
    def _get_scientometrics_query() -> str:
        """Construct parameterized Cypher Query 2 with isolated CALL blocks."""
        return SCIENTOMETRICS_QUERY

    async def extract_scientometrics(self, project_id: str) -> ScientometricFacts:
        """Execute Query 2: Deterministically aggregate literature metrics from Neo4j."""
        records = await self.neo4j.execute_read(self._get_scientometrics_query(), {"project_id": project_id})
        landmarks = await self.extract_landmark_papers(project_id)
        if not records or records[0].get("total_papers", 0) == 0:
            return self._build_default_scientometrics(landmarks)
        return self._map_scientometrics_record(records[0], landmarks)

    def _map_scientometrics_record(
        self, row: dict[str, Any], landmarks: list[dict[str, Any]]
    ) -> ScientometricFacts:
        """Map query row into ScientometricFacts Pydantic model."""
        years = self._parse_year_distribution(row.get("year_distribution") or [])
        return ScientometricFacts(
            total_papers=int(row.get("total_papers") or 0),
            total_citations=int(row.get("total_citations") or 0),
            unique_authors=int(row.get("unique_authors") or 0),
            year_distribution=years,
            top_venues=row.get("top_venues") or [],
            top_authors=row.get("top_authors") or [],
            landmark_papers=landmarks,
        )

    def _parse_year_distribution(self, raw_years: list[dict[str, Any]]) -> dict[int, int]:
        """Convert year distribution query records into integer key-value mapping."""
        res: dict[int, int] = {}
        for item in raw_years:
            yr = int(item.get("year") or 0)
            cnt = int(item.get("count") or 0)
            if yr > 0:
                res[yr] = cnt
        return res

    def _build_default_scientometrics(self, landmarks: list[dict[str, Any]]) -> ScientometricFacts:
        """Construct zeroed scientometrics structure for empty libraries."""
        return ScientometricFacts(
            total_papers=0,
            total_citations=0,
            unique_authors=0,
            year_distribution={},
            top_venues=[],
            top_authors=[],
            landmark_papers=landmarks,
        )

    @staticmethod
    def _map_landmark_record(r: dict[str, Any]) -> dict[str, Any]:
        """Format individual landmark paper row from Neo4j record."""
        return {
            "doi": str(r.get("doi") or ""),
            "title": str(r.get("title") or "Untitled"),
            "year": int(r.get("year") or 2024),
            "venue": str(r.get("venue") or "Unknown Venue"),
            "external_citations": int(r.get("external_citations") or 0),
            "in_graph_citations": int(r.get("in_graph_citations") or 0),
            "summary": str(r.get("summary") or ""),
        }

    async def extract_landmark_papers(self, project_id: str, limit: int = 6) -> list[dict[str, Any]]:
        """Execute Query 3: Extract landmark papers ranked by PageRank or citation centrality."""
        query = (
            "MATCH (proj:Project {project_id: $project_id})-[:HAS_PAPER|CONTAINS_PAPER]->(p:Paper)\n"
            "OPTIONAL MATCH (p)<-[:CITES]-(citing:Paper)\n"
            "WITH p, count(citing) AS in_graph_citations\n"
            "ORDER BY coalesce(p.pagerank, in_graph_citations) DESC, "
            "coalesce(p.cited_by_count, p.citation_count, 0) DESC\n"
            "LIMIT $limit\n"
            "RETURN p.doi AS doi, p.title AS title, coalesce(p.year, 2024) AS year, "
            "coalesce(p.venue, 'Unknown Venue') AS venue, "
            "coalesce(p.cited_by_count, p.citation_count, 0) AS external_citations, "
            "in_graph_citations, coalesce(p.key_insight, p.abstract, '') AS summary"
        )
        records = await self.neo4j.execute_read(query, {"project_id": project_id, "limit": limit})
        return [self._map_landmark_record(r) for r in records if r.get("doi")]

    @staticmethod
    def _map_matrix_record(r: dict[str, Any]) -> SynthesisMatrixFact:
        """Construct SynthesisMatrixFact from Cypher query record."""
        default_dims = ["Architecture", "Datasets", "Loss Function", "Strengths", "Limitations"]
        return SynthesisMatrixFact(
            section_id=str(r.get("section_id") or "sec-unknown"),
            section_title=str(r.get("section_title") or "Synthesis Matrix"),
            dimensions=list(r.get("dimensions") or default_dims),
            matrix_markdown=str(r.get("matrix_markdown") or ""),
            paper_count=int(r.get("paper_count") or 0),
        )

    async def extract_synthesis_matrices(self, project_id: str) -> list[SynthesisMatrixFact]:
        """Execute Query 4: Extract approved section synthesis comparison matrices."""
        query = (
            "MATCH (proj:Project {project_id: $project_id})-[:HAS_OUTLINE_SECTION]->(sec:OutlineSection)\n"
            "OPTIONAL MATCH (sec)-[:HAS_MATRIX|HAS_SYNTHESIS_MATRIX]->(m:SectionSynthesisMatrix)\n"
            "OPTIONAL MATCH (m)-[:SYNTHESIZES]->(p:Paper)\n"
            "WITH sec, m, count(DISTINCT p) AS reviewed_papers\n"
            "ORDER BY coalesce(sec.order, 0) ASC\n"
            "RETURN sec.section_id AS section_id, sec.title AS section_title, "
            "coalesce(m.dimensions, ['Architecture', 'Datasets', 'Loss Function', 'Strengths', 'Limitations']) "
            "AS dimensions, coalesce(m.matrix_markdown, m.markdown_path, '') AS matrix_markdown, "
            "reviewed_papers AS paper_count"
        )
        records = await self.neo4j.execute_read(query, {"project_id": project_id})
        return [self._map_matrix_record(r) for r in records]

    @staticmethod
    def _map_pathway_record(r: dict[str, Any]) -> SvplPathwayFact | None:
        """Map SVPL multi-hop pathway record to Pydantic model."""
        from_doi = str(r.get("from_doi") or "")
        to_doi = str(r.get("to_doi") or "")
        if not from_doi or not to_doi:
            return None
        return SvplPathwayFact(
            from_doi=from_doi,
            to_doi=to_doi,
            intermediate_dois=[str(d) for d in (r.get("intermediate_dois") or [])],
            bridge_mechanism=str(r.get("bridge_mechanism") or "direct"),
            hop_count=max(1, min(3, int(r.get("hop_count") or 2))),
            confidence=1.0,
        )

    async def extract_svpl_pathways(self, project_id: str) -> list[SvplPathwayFact]:
        """Execute Query 5: Extract discovered SVPL multi-hop citation pathways."""
        query = (
            "MATCH (proj:Project {project_id: $project_id})-[:HAS_PAPER|CONTAINS_PAPER]->(source:Paper)\n"
            "MATCH (source)-[b:BRIDGES]->(target:Paper)\n"
            "RETURN source.doi AS from_doi, target.doi AS to_doi, "
            "coalesce(b.intermediate_nodes, []) AS intermediate_dois, "
            "coalesce(b.mechanism, 'direct') AS bridge_mechanism, "
            "coalesce(b.hop_distance, 2) AS hop_count\n"
            "ORDER BY hop_count ASC\n"
            "LIMIT 5"
        )
        records = await self.neo4j.execute_read(query, {"project_id": project_id})
        results: list[SvplPathwayFact] = []
        for r in records:
            fact = self._map_pathway_record(r)
            if fact:
                results.append(fact)
        return results

    async def extract_all_project_facts(self, project_id: str) -> ProjectEpistemicFacts:
        """Coordinate full fact extraction pipeline with empty-library scoping fallback."""
        meta, rqs = await self.extract_project_metadata_and_rqs(project_id)
        sciento = await self.extract_scientometrics(project_id)
        if sciento.total_papers == 0:
            return self._build_fallback_facts(meta, rqs)
        matrices = await self.extract_synthesis_matrices(project_id)
        pathways = await self.extract_svpl_pathways(project_id)
        return ProjectEpistemicFacts(
            project_id=meta["project_id"],
            project_name=meta["project_name"],
            domain=meta["domain"],
            description=meta["description"],
            creation_date=meta["creation_date"],
            workflow_stage=meta["workflow_stage"],
            research_questions=rqs,
            scientometrics=sciento,
            synthesis_matrices=matrices,
            svpl_pathways=pathways,
            empty_library_warning=False,
        )

    def _build_fallback_facts(
        self, meta: dict[str, Any], rqs: list[ResearchQuestionFact]
    ) -> ProjectEpistemicFacts:
        """Package scoping deck fallback container for zero-paper campaigns."""
        logger.warning(
            "Scoping fallback activated for campaign %s: zero papers found", meta["project_id"]
        )
        return ProjectEpistemicFacts(
            project_id=meta["project_id"],
            project_name=meta["project_name"],
            domain=meta["domain"],
            description=meta["description"],
            creation_date=meta["creation_date"],
            workflow_stage=meta["workflow_stage"],
            research_questions=rqs,
            scientometrics=self._build_default_scientometrics([]),
            synthesis_matrices=[],
            svpl_pathways=[],
            empty_library_warning=True,
        )
