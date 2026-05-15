import asyncio
import logging
import math
import re
from collections.abc import Callable

from models.openalex_models import Work
from models.graph_node import GraphNode
from models.ranked_paper import RankedPaper
from models.progress import GraphSearchProgress, GraphSearchStatus
from services.gemini_service import GeminiService
from services.openalex_service import OpenAlexService

logger = logging.getLogger(__name__)

# Type alias for progress callback
ProgressCallback = Callable[[GraphSearchProgress], None] | None

# Type alias for paper-level event callback (processing / found / skipped)
PaperEventCallback = Callable[[dict[str, object]], None] | None


class GraphSearchService:
    """GraphSelect Algorithm Service.

    Implements the GraphSelect algorithm for semantic paper search:
    1. Embed research questions via Gemini
    2. Start from seed paper, embed its abstract
    3. Traverse citations and references via BFS
    4. Filter by cosine similarity threshold
    5. Recursively explore relevant papers up to max depth
    6. Rank results using PageRank + similarity

    Ported from Dart GraphSearchService in graph_search_service.dart.
    """

    def __init__(
        self,
        research_questions: list[str],
        seed_doi: str,
        api_key: str,
        similarity_threshold: float = 0.3,
        max_depth: int = 3,
        max_neighbors_per_level: int = 25,
        on_progress: ProgressCallback = None,
        on_paper_event: PaperEventCallback = None,
        openalex_email: str | None = None,
        embedding_model: str = 'gemini-embedding-001',
        pagerank_iterations: int = 20,
        pagerank_damping: float = 0.85,
        similarity_weight: float = 0.7,
        pagerank_weight: float = 0.3,
        rate_limit_delay_ms: int = 100,
    ) -> None:
        # Configuration
        self.research_questions: list[str] = research_questions
        self.seed_doi: str = seed_doi
        self.similarity_threshold: float = similarity_threshold
        self.max_depth: int = max_depth
        self.max_neighbors_per_level: int = max_neighbors_per_level
        self.on_progress: ProgressCallback = on_progress
        self.on_paper_event: PaperEventCallback = on_paper_event
        self.pagerank_iterations: int = pagerank_iterations
        self.pagerank_damping: float = pagerank_damping
        self.similarity_weight: float = similarity_weight
        self.pagerank_weight: float = pagerank_weight
        self.rate_limit_delay_ms: int = rate_limit_delay_ms

        # Services
        self._gemini: GeminiService = GeminiService(api_key=api_key, model=embedding_model)
        self._openalex: OpenAlexService = OpenAlexService(email=openalex_email)

        # Internal state
        self._graph: dict[str, GraphNode] = {}
        self._visited: set[str] = set()
        self._question_embeddings: dict[str, list[float]] = {}
        self._total_papers_processed: int = 0
        self._total_api_calls: int = 0

    @property
    def graph(self) -> dict[str, GraphNode]:
        """Get the constructed graph (read-only copy)."""
        return dict(self._graph)

    @property
    def total_papers_processed(self) -> int:
        return self._total_papers_processed

    @property
    def total_api_calls(self) -> int:
        return self._total_api_calls

    async def search(self) -> list[RankedPaper]:
        """Run the complete GraphSelect search algorithm.

        Returns:
            Ranked list of papers sorted by combined score (descending).
        """
        try:
            # Phase 1: Embed research questions
            self._report_progress(GraphSearchProgress(
                status=GraphSearchStatus.EMBEDDING_QUESTIONS,
                message='Embedding research questions...',
            ))
            await self._embed_questions()

            # Phase 2: Process seed paper
            self._report_progress(GraphSearchProgress(
                status=GraphSearchStatus.PROCESSING_SEED,
                message='Processing seed paper...',
            ))
            seed_node: GraphNode | None = await self._process_seed_paper()
            if seed_node is None:
                raise RuntimeError('Failed to process seed paper')

            # Phase 3: Explore graph recursively
            await self._explore_graph(seed_node, 1)

            # Phase 4: Calculate PageRank and rank results
            self._report_progress(GraphSearchProgress(
                status=GraphSearchStatus.CALCULATING_PAGERANK,
                message='Calculating rankings...',
                relevant_papers_found=len(self._graph),
            ))
            pagerank_scores: dict[str, float] = self._calculate_pagerank()
            results: list[RankedPaper] = self._generate_ranked_results(pagerank_scores)

            self._report_progress(GraphSearchProgress(
                status=GraphSearchStatus.COMPLETED,
                message='Search completed!',
                relevant_papers_found=len(results),
            ))

            return results

        except Exception as e:
            logger.error(f'Graph search failed: {e}', exc_info=True)
            self._report_progress(GraphSearchProgress(
                status=GraphSearchStatus.ERROR,
                error_message=str(e),
            ))
            raise
        finally:
            await self._openalex.close()

    async def _embed_questions(self) -> None:
        """Embed all research questions via Gemini."""
        for question in self.research_questions:
            if not question.strip():
                continue
            logger.info(f'Embedding question: "{question}"')
            embedding: list[float] = await self._gemini.get_embedding(question)
            self._total_api_calls += 1
            if embedding:
                self._question_embeddings[question] = embedding
        logger.info(f'Embedded {len(self._question_embeddings)} questions')

    async def _process_seed_paper(self) -> GraphNode | None:
        """Process the seed paper: fetch, embed, score, and add to graph."""
        try:
            work: Work = await self._openalex.get_work(self.seed_doi)
            self._total_api_calls += 1

            self._report_paper_event({
                'id': work.id or self.seed_doi,
                'title': work.title or '',
                'status': 'processing',
            })

            abstract_text: str = self._extract_abstract(work)
            if not abstract_text:
                logger.warning('Seed paper has no abstract')

            # Embed abstract
            embedding: list[float] = []
            if abstract_text:
                embedding = await self._gemini.get_embedding(abstract_text)
                self._total_api_calls += 1

            # Calculate scores (seed always included)
            scores: dict[str, float] = self._calculate_question_scores(embedding)

            # Get citation and reference IDs
            citation_ids: list[str] = await self._fetch_citation_ids(work)
            reference_ids: list[str] = self._extract_reference_ids(work)

            node = GraphNode(
                work=work,
                abstract_text=abstract_text,
                embedding=embedding,
                question_scores=scores,
                citations=set(citation_ids),
                references=set(reference_ids),
                discovered_at_depth=0,
            )

            node_id: str = node.openalex_id
            self._graph[node_id] = node
            self._visited.add(node_id)
            self._total_papers_processed += 1

            self._report_paper_event({
                'id': node_id,
                'title': work.title or '',
                'depth': 0,
                'similarity': node.max_score,
                'status': 'found',
            })

            logger.info(f'Seed paper added: {work.title}')
            logger.info(f'  Citations: {len(citation_ids)}, References: {len(reference_ids)}')

            return node

        except Exception as e:
            logger.error(f'Failed to process seed paper: {e}', exc_info=True)
            return None

    async def _explore_graph(self, start_node: GraphNode, current_depth: int) -> None:
        """Explore the graph from current level papers via BFS."""
        if current_depth > self.max_depth:
            return

        self._report_progress(GraphSearchProgress(
            status=GraphSearchStatus.EXPLORING_LEVEL,
            current_depth=current_depth,
            max_depth=self.max_depth,
            relevant_papers_found=len(self._graph),
            message=f'Exploring level {current_depth}...',
        ))

        # Get papers at previous depth level
        papers_at_current_level: list[GraphNode] = [
            n for n in self._graph.values()
            if n.discovered_at_depth == current_depth - 1
        ]

        # Collect neighbors with parent tracking:
        # Each entry is (neighbor_id, parent_openalex_id, relationship_type)
        neighbor_entries: list[tuple[str, str, str]] = []
        seen_neighbors: set[str] = set()

        for paper in papers_at_current_level:
            parent_id: str = paper.openalex_id
            for ref_id in paper.references:
                if ref_id not in self._visited and ref_id not in seen_neighbors:
                    seen_neighbors.add(ref_id)
                    neighbor_entries.append((ref_id, parent_id, 'reference'))
            for cit_id in paper.citations:
                if cit_id not in self._visited and cit_id not in seen_neighbors:
                    seen_neighbors.add(cit_id)
                    neighbor_entries.append((cit_id, parent_id, 'citation'))

        # Limit to max neighbors
        max_count: int = self.max_neighbors_per_level * len(papers_at_current_level)
        neighbor_entries = neighbor_entries[:max_count]

        logger.info(f'Level {current_depth}: Processing {len(neighbor_entries)} potential papers')

        processed: int = 0
        new_relevant_nodes: list[GraphNode] = []

        for neighbor_id, parent_oa_id, relationship in neighbor_entries:
            if neighbor_id in self._visited:
                continue
            self._visited.add(neighbor_id)

            processed += 1
            self._report_progress(GraphSearchProgress(
                status=GraphSearchStatus.EXPLORING_LEVEL,
                current_depth=current_depth,
                max_depth=self.max_depth,
                relevant_papers_found=len(self._graph),
                current_level_progress=processed,
                current_level_total=len(neighbor_entries),
                message=f'Processing paper {processed}/{len(neighbor_entries)}...',
            ))

            try:
                # Fetch work details
                work: Work = await self._openalex.get_work(neighbor_id)
                self._total_api_calls += 1
                self._total_papers_processed += 1

                self._report_paper_event({
                    'id': neighbor_id,
                    'title': work.title or '',
                    'status': 'processing',
                    'parent_id': parent_oa_id,
                    'relationship': relationship,
                    'depth': current_depth,
                })

                abstract_text: str = self._extract_abstract(work)
                if not abstract_text:
                    logger.debug(f'Skipping paper without abstract: {work.title}')
                    self._report_paper_event({
                        'id': neighbor_id,
                        'title': work.title or '',
                        'status': 'skipped',
                        'reason': 'no_abstract',
                        'parent_id': parent_oa_id,
                        'relationship': relationship,
                        'depth': current_depth,
                    })
                    continue

                # Embed abstract
                embedding: list[float] = await self._gemini.get_embedding(abstract_text)
                self._total_api_calls += 1

                if not embedding:
                    self._report_paper_event({
                        'id': neighbor_id,
                        'title': work.title or '',
                        'status': 'skipped',
                        'reason': 'embedding_failed',
                        'parent_id': parent_oa_id,
                        'relationship': relationship,
                        'depth': current_depth,
                    })
                    continue

                # Check relevance
                scores: dict[str, float] = self._calculate_question_scores(embedding)
                is_relevant: bool = self._is_relevant(scores)

                if is_relevant:
                    # Fetch citations/references for future exploration
                    citation_ids: list[str] = await self._fetch_citation_ids(work)
                    reference_ids: list[str] = self._extract_reference_ids(work)

                    node = GraphNode(
                        work=work,
                        abstract_text=abstract_text,
                        embedding=embedding,
                        question_scores=scores,
                        citations=set(citation_ids),
                        references=set(reference_ids),
                        discovered_at_depth=current_depth,
                    )

                    node_id: str = OpenAlexService.extract_openalex_id(work) or work.id or ''
                    self._graph[node_id] = node
                    new_relevant_nodes.append(node)

                    self._report_paper_event({
                        'id': node_id,
                        'title': work.title or '',
                        'depth': current_depth,
                        'similarity': node.max_score,
                        'status': 'found',
                        'parent_id': parent_oa_id,
                        'relationship': relationship,
                    })

                    logger.info(f'Relevant paper found: {work.title} (score: {node.max_score:.3f})')
                else:
                    max_score: float = max(scores.values()) if scores else 0.0
                    self._report_paper_event({
                        'id': neighbor_id,
                        'title': work.title or '',
                        'status': 'skipped',
                        'reason': f'below_threshold ({max_score:.3f} < {self.similarity_threshold})',
                        'parent_id': parent_oa_id,
                        'relationship': relationship,
                        'depth': current_depth,
                    })

                # Rate limit delay
                await asyncio.sleep(self.rate_limit_delay_ms / 1000.0)

            except Exception as e:
                logger.warning(f'Failed to process neighbor {neighbor_id}: {e}')

        logger.info(f'Level {current_depth} complete: Found {len(new_relevant_nodes)} relevant papers')

        # Recursively explore next level
        if new_relevant_nodes and current_depth < self.max_depth:
            await self._explore_graph(new_relevant_nodes[0], current_depth + 1)

    def _extract_abstract(self, work: Work) -> str:
        """Extract abstract from work (reconstruct from inverted index)."""
        if work.abstract_inverted_index:
            return OpenAlexService.reconstruct_abstract(work.abstract_inverted_index)
        return ''

    async def _fetch_citation_ids(self, work: Work) -> list[str]:
        """Fetch citation IDs for a work."""
        try:
            work_id: str | None = OpenAlexService.extract_openalex_id(work)
            if not work_id:
                return []

            response = await self._openalex.get_citations(
                work_id,
                per_page=self.max_neighbors_per_level,
                sort='cited_by_count:desc',
            )
            self._total_api_calls += 1

            ids: list[str] = []
            for w in response.results:
                oa_id: str | None = OpenAlexService.extract_openalex_id(w)
                if oa_id:
                    ids.append(oa_id)
            return ids

        except Exception as e:
            logger.warning(f'Failed to fetch citations: {e}')
            return []

    def _extract_reference_ids(self, work: Work) -> list[str]:
        """Extract reference IDs from work's referenced_works field."""
        ids: list[str] = []
        for url in work.referenced_works:
            match = re.search(r'W\d+', url)
            if match:
                ids.append(match.group(0))
                if len(ids) >= self.max_neighbors_per_level:
                    break
        return ids

    def _calculate_question_scores(self, abstract_embedding: list[float]) -> dict[str, float]:
        """Calculate cosine similarity scores between abstract and all question embeddings."""
        if not abstract_embedding:
            return {}

        scores: dict[str, float] = {}
        for question, q_embedding in self._question_embeddings.items():
            scores[question] = self.cosine_similarity(abstract_embedding, q_embedding)
        return scores

    def _is_relevant(self, scores: dict[str, float]) -> bool:
        """Check if any question score exceeds the similarity threshold."""
        return any(score >= self.similarity_threshold for score in scores.values())

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """Calculate cosine similarity between two vectors.

        Returns 0.0 if vectors are empty, different lengths, or have zero magnitude.
        """
        if len(a) != len(b) or not a:
            return 0.0

        dot_product: float = 0.0
        norm_a: float = 0.0
        norm_b: float = 0.0

        for i in range(len(a)):
            dot_product += a[i] * b[i]
            norm_a += a[i] * a[i]
            norm_b += b[i] * b[i]

        magnitude: float = math.sqrt(norm_a) * math.sqrt(norm_b)
        if magnitude == 0:
            return 0.0

        return dot_product / magnitude

    def _calculate_pagerank(
        self,
        iterations: int | None = None,
        damping_factor: float | None = None,
    ) -> dict[str, float]:
        """Calculate PageRank scores for the filtered graph.

        Uses iterative power method.
        """
        iters: int = iterations if iterations is not None else self.pagerank_iterations
        damping: float = damping_factor if damping_factor is not None else self.pagerank_damping

        n: int = len(self._graph)
        if n == 0:
            return {}

        # Initialize uniform scores
        scores: dict[str, float] = {node_id: 1.0 / n for node_id in self._graph}

        # Iterate
        for _ in range(iters):
            new_scores: dict[str, float] = {}

            for node_id in self._graph:
                incoming_sum: float = 0.0

                for other_id, other_node in self._graph.items():
                    # Check if other cites or references current node
                    if node_id in other_node.citations or node_id in other_node.references:
                        out_degree: int = len(other_node.citations) + len(other_node.references)
                        if out_degree > 0:
                            incoming_sum += scores[other_id] / out_degree

                new_scores[node_id] = (1 - damping) / n + damping * incoming_sum

            scores = new_scores

        return scores

    def _generate_ranked_results(self, pagerank_scores: dict[str, float]) -> list[RankedPaper]:
        """Generate ranked results combining similarity and PageRank."""
        # Normalize PageRank scores
        max_pr: float = max(pagerank_scores.values()) if pagerank_scores else 1.0

        results: list[RankedPaper] = []

        for node_id, node in self._graph.items():
            pr_score: float = pagerank_scores.get(node_id, 0.0)
            normalized_pr: float = pr_score / max_pr if max_pr > 0 else 0.0

            # Combined score: similarity_weight * similarity + pagerank_weight * PageRank
            combined_score: float = (
                self.similarity_weight * node.max_score +
                self.pagerank_weight * normalized_pr
            )

            results.append(RankedPaper(
                work=node.work,
                abstract_text=node.abstract_text,
                max_similarity_score=node.max_score,
                pagerank_score=normalized_pr,
                combined_score=combined_score,
                depth=node.discovered_at_depth,
                question_scores=dict(node.question_scores),
            ))

        # Sort by combined score descending
        results.sort(key=lambda r: r.combined_score, reverse=True)

        return results

    def _report_progress(self, progress: GraphSearchProgress) -> None:
        """Report progress to callback if set."""
        if self.on_progress:
            self.on_progress(progress)

    def _report_paper_event(self, event: dict[str, object]) -> None:
        """Report a paper-level event to callback if set."""
        if self.on_paper_event:
            self.on_paper_event(event)
