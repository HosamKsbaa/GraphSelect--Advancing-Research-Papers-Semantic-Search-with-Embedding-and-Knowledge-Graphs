from __future__ import annotations

import json
from pathlib import Path
import pytest
from pydantic import SecretStr

from ai import AgentToolRuntime, GeminiModelClient, ModelClientSettings, ResearchAgent
from engines.alrs import AlrsDiscoverRequest, AlrsEngine
from engines.collections import InMemoryCollectionStore
from engines.openalex import OpenAlexWork


class FakeEmbeddingProvider:
    async def embed_text(self, text: str) -> list[float]:
        lowered = text.lower()
        if "unrelated" in lowered or "cooking" in lowered:
            return [0.0, 1.0, 0.0]
        return [1.0, 0.0, 0.0]


class FakeOpenAlexProvider:
    def __init__(self) -> None:
        self.works: dict[str, OpenAlexWork] = {
            "10.1000/seed": OpenAlexWork.model_validate(
                {
                    "id": "https://openalex.org/W100",
                    "doi": "10.1000/seed",
                    "title": "GraphSelect: Hybrid Semantic and Citation Graph Retrieval",
                    "publication_year": 2025,
                    "cited_by_count": 42,
                    "abstract": "GraphSelect combines dense embeddings with personalized PageRank. It improves retrieval recall on sparse citation subgraphs.",
                    "authorships": [
                        {"author": {"display_name": "Alice Researcher"}},
                        {"author": {"display_name": "Bob Scholar"}},
                    ],
                    "primary_location": {"source": {"display_name": "Journal of Information Retrieval"}},
                    "referenced_works": [
                        "https://openalex.org/W101",
                        "https://openalex.org/W102",
                    ],
                }
            ),
            "10.1000/ref1": OpenAlexWork.model_validate(
                {
                    "id": "https://openalex.org/W101",
                    "doi": "10.1000/ref1",
                    "title": "Density-Gated PageRank for Academic Literature",
                    "publication_year": 2024,
                    "cited_by_count": 19,
                    "abstract": "Density gating disables noisy random walks when citation edge density is below threshold. Pure cosine similarity ranks sparse graphs reliably.",
                    "authorships": [{"author": {"display_name": "Carol Scientist"}}],
                    "primary_location": {"source": {"display_name": "SIGIR"}},
                    "referenced_works": [],
                }
            ),
            "10.1000/ref2": OpenAlexWork.model_validate(
                {
                    "id": "https://openalex.org/W102",
                    "doi": "10.1000/ref2",
                    "title": "Unrelated Cooking Recipes and Culinary Notes",
                    "publication_year": 2020,
                    "cited_by_count": 2,
                    "abstract": "Unrelated cooking instructions for baking sourdough bread.",
                    "authorships": [{"author": {"display_name": "Chef Baker"}}],
                    "primary_location": {"source": {"display_name": "Culinary Monthly"}},
                    "referenced_works": [],
                }
            ),
        }
        self._by_id = {w.id: w for w in self.works.values() if w.id is not None}

    async def search_works(
        self, query: str, *, per_page: int | None = None
    ) -> list[OpenAlexWork]:
        assert query
        limit = per_page if per_page is not None else 10
        return [self.works["10.1000/seed"], self.works["10.1000/ref1"]][:limit]

    async def get_work_by_doi(self, doi: str) -> OpenAlexWork | None:
        return self.works.get(doi)

    async def get_works_batch(
        self, openalex_ids: list[str]
    ) -> tuple[list[OpenAlexWork], list[str], list[str]]:
        found = [self._by_id[oid] for oid in openalex_ids if oid in self._by_id]
        return found, [], []


@pytest.mark.asyncio
async def test_alrs_engine_discover_filters_and_ranks() -> None:
    openalex = FakeOpenAlexProvider()
    embeddings = FakeEmbeddingProvider()
    engine = AlrsEngine(openalex=openalex, embeddings=embeddings)

    events: list[str] = []
    result = await engine.discover(
        AlrsDiscoverRequest(
            seed_doi="10.1000/seed",
            research_questions=["How does density-gated PageRank improve citation search?"],
            similarity_threshold=0.5,
            max_depth=1,
        ),
        on_progress=lambda stage, _msg, _d, _m: events.append(stage),
    )

    assert result.seed_doi == "10.1000/seed"
    dois = [node.paper.doi for node in result.nodes]
    assert "10.1000/seed" in dois
    assert "10.1000/ref1" in dois
    assert "10.1000/ref2" not in dois
    assert "embedding_questions" in events
    assert "completed" in events


@pytest.mark.asyncio
async def test_research_agent_end_to_end_and_tools() -> None:
    openalex = FakeOpenAlexProvider()
    embeddings = FakeEmbeddingProvider()
    engine = AlrsEngine(openalex=openalex, embeddings=embeddings)
    store = InMemoryCollectionStore()
    runtime = AgentToolRuntime(
        openalex=openalex,
        alrs_engine=engine,
        collection_store=store,
    )

    tools = runtime.build_langchain_tools()
    assert [t.name for t in tools] == [
        "search_papers",
        "discover_literature",
        "get_collection",
        "write_review",
    ]

    agent = ResearchAgent(runtime)
    review = await agent.run(
        topic="How does GraphSelect rank academic literature?",
        research_questions=["How does GraphSelect combine embeddings and PageRank?"],
    )

    assert review.verified_findings_count == 1
    assert "10.1000/seed" in review.cited_dois
    assert "[10.1000/seed]" in review.markdown_review
    assert "## References" in review.markdown_review
    assert any("@article" in entry for entry in review.bibtex_entries)


@pytest.mark.asyncio
async def test_smoke_topics_fixture_runs_through_agent() -> None:
    topics_path = Path(__file__).resolve().parents[2] / "evals" / "smoke_topics.json"
    topics = json.loads(topics_path.read_text(encoding="utf-8"))
    assert len(topics) == 5

    openalex = FakeOpenAlexProvider()
    embeddings = FakeEmbeddingProvider()
    runtime = AgentToolRuntime(
        openalex=openalex,
        alrs_engine=AlrsEngine(openalex=openalex, embeddings=embeddings),
    )
    agent = ResearchAgent(runtime)

    for item in topics:
        output = await agent.run(
            topic=item["topic"],
        )
        assert output.verified_findings_count >= 1
        assert output.cited_dois


def test_model_client_builder_instantiates() -> None:
    client = GeminiModelClient(
        ModelClientSettings(gemini_api_key=SecretStr("test-key"), default_model="gemini-2.5-flash")
    )
    assert client.configured
    assert client.model_name == "gemini-2.5-flash"
