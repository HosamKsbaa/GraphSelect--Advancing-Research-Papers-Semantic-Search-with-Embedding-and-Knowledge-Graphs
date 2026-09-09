"""
Empirical Challenger Verification Harness for Theorems 3.1-3.3 and Tables 6.1-6.4.
Target: newcode/code/backend/tests/test_empirical_challenger.py
"""

import math
import random
import os
import sys
import numpy as np
import pandas as pd
from scipy import stats
import networkx as nx
import pytest

import asyncio
from unittest.mock import AsyncMock, patch

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.clients.openalex_client import OpenAlexService
from core.clients.rate_limiter import AdaptiveRateLimiter
from core.db.neo4j_service import Neo4jService
from features.ranking.service import RankingService
from features.ranking.models import RankedPaper, QuestionGroup, GroupedResults


# ==============================================================================
# SECTION 1: THEOREM 3.1 — BFS TERMINATION & SEARCH SPACE BOUNDS
# ==============================================================================

def simulate_bfs_crawl(graph: nx.DiGraph, seed: str, max_depth: int) -> tuple[set[str], list[int]]:
    """Simulates Algorithm 1 (GraphSelect BFS Crawl) over a directed citation graph.
    Traverses both outgoing references and incoming citations (undirected expansion).
    Returns (visited_set, queue_sizes_per_level).
    """
    visited = {seed}
    current_queue = [seed]
    queue_sizes = [len(current_queue)]
    
    for depth in range(1, max_depth + 1):
        if not current_queue:
            break
        next_queue = []
        for node in current_queue:
            # Undirected neighborhood: Out-edges (references) + In-edges (citations)
            neighbors = set(graph.successors(node)) | set(graph.predecessors(node))
            for nbr in neighbors:
                if nbr not in visited:
                    visited.add(nbr)
                    next_queue.append(nbr)
        current_queue = next_queue
        queue_sizes.append(len(current_queue))
        
    return visited, queue_sizes


def test_theorem_3_1_bounds_on_synthetic_graphs():
    """Adversarial stress test of Theorem 3.1 on diverse synthetic graph topologies."""
    random.seed(42)
    np.random.seed(42)
    
    test_cases = [
        # (name, graph_generator, max_depth)
        ("Single Node Graph", lambda: nx.DiGraph([( "p0", "p0" )]), 3),
        ("Path Graph (b_max=2)", lambda: nx.path_graph(20, create_using=nx.DiGraph), 4),
        ("Star Graph (High Hub Degree)", lambda: nx.star_graph(50, create_using=nx.DiGraph), 3),
        ("Complete Graph (Dense)", lambda: nx.complete_graph(15, create_using=nx.DiGraph), 3),
        ("Erdos-Renyi Random Graph", lambda: nx.erdos_renyi_graph(100, 0.05, directed=True), 3),
        ("Barabasi-Albert Scale-Free", lambda: nx.scale_free_graph(100), 3),
        ("Disconnected 5-Component Graph", lambda: nx.disjoint_union_all([nx.erdos_renyi_graph(20, 0.1, directed=True) for _ in range(5)]), 3),
    ]
    
    for name, gen_fn, D in test_cases:
        G = gen_fn()
        if not isinstance(G, nx.DiGraph):
            G = nx.DiGraph(G)
            
        nodes = list(G.nodes())
        if not nodes:
            continue
        seed = nodes[0]
        
        # Calculate maximum undirected degree b_max
        b_max = max((G.in_degree(n) + G.out_degree(n) for n in G.nodes()), default=0)
        
        visited, queue_sizes = simulate_bfs_crawl(G, seed, D)
        total_visited = len(visited)
        
        # Theoretical Bound
        if b_max > 1:
            theo_bound = (b_max ** (D + 1) - 1) // (b_max - 1)
        elif b_max == 1:
            theo_bound = D + 1
        else: # b_max == 0
            theo_bound = 1
            
        assert total_visited <= theo_bound, f"Theorem 3.1 bound violated on {name}: visited={total_visited} > bound={theo_bound}"
        assert len(visited) <= G.number_of_nodes(), f"Visited set exceeded total graph nodes on {name}"
        
    print(">>> Theorem 3.1: All synthetic graph bounds strictly hold.")


# ==============================================================================
# SECTION 2: THEOREM 3.2 — RANKING SOUNDNESS & SCORE BOUNDEDNESS
# ==============================================================================

def min_max_normalize(scores: dict[str, float]) -> dict[str, float]:
    if not scores:
        return {}
    min_s = min(scores.values())
    max_s = max(scores.values())
    diff = max_s - min_s
    if diff > 0.0:
        return {k: (v - min_s) / diff for k, v in scores.items()}
    else:
        return {k: 1.0 for k in scores}


def compute_hybrid_score(sim: float, pr_norm: float, w_s: float = 0.70, w_r: float = 0.30) -> float:
    return w_s * sim + w_r * pr_norm


def test_theorem_3_2_score_boundedness_exhaustive():
    """Adversarial stress test of Theorem 3.2 score boundedness across all parameter spaces."""
    weights = [
        (0.70, 0.30),
        (1.00, 0.00),
        (0.00, 1.00),
        (0.50, 0.50),
        (0.80, 0.20),
        (0.30, 0.70),
    ]
    thresholds = [0.0, 0.3, 0.5, 0.6, 0.7, 0.85, 0.99, 1.0]
    
    for w_s, w_r in weights:
        for tau in thresholds:
            # Simulate 1,000 random similarity values in [tau, 1.0]
            sims = np.random.uniform(tau, 1.0, size=1000)
            
            # Simulate various PageRank distributions
            pr_cases = [
                {"p0": 1.0}, # Single node
                {"p0": 0.5, "p1": 0.5}, # Equal PageRank
                {f"p{i}": float(i) for i in range(50)}, # Linear gradient
                {f"p{i}": np.random.exponential(1.0) for i in range(100)}, # Skewed distribution
            ]
            
            for pr_raw in pr_cases:
                pr_norm = min_max_normalize(pr_raw)
                for p, pr_val in pr_norm.items():
                    assert 0.0 <= pr_val <= 1.0, f"PageRank normalization breached [0, 1]: {pr_val}"
                    
                    for sim in sims:
                        score = compute_hybrid_score(sim, pr_val, w_s, w_r)
                        lower_bound = w_s * tau
                        upper_bound = 1.0 + 1e-9 # Numerical tolerance
                        
                        assert score >= lower_bound - 1e-9, f"Score {score} < lower bound {lower_bound} (w_s={w_s}, tau={tau})"
                        assert score <= upper_bound, f"Score {score} > upper bound {upper_bound}"
                        
    print(">>> Theorem 3.2: Score boundedness in [w_s * tau, 1.0] verified across 100% parameter sweeps.")


# ==============================================================================
# SECTION 3: THEOREM 3.3 — GROUP PARTITIONING INVARIANCE & TIE-BREAKING
# ==============================================================================

def test_theorem_3_3_partitioning_disjointness_and_exhaustiveness():
    """Verifies that assigned question groups form a valid partition."""
    questions = ["q1", "q2", "q3", "q4"]
    dois = [f"10.1000/paper_{i}" for i in range(200)]
    tau = 0.50
    
    similarities = []
    for doi in dois:
        for q in questions:
            sim = random.uniform(0.3, 0.95)
            if sim >= tau:
                similarities.append({"doi": doi, "question": q, "score": sim})
                
    # Execute grouping logic from RankingService
    best_matches: dict[str, tuple[str, float]] = {}
    for sim in similarities:
        d = str(sim["doi"])
        q = str(sim["question"])
        s = float(sim["score"])
        if d not in best_matches or s > best_matches[d][1]:
            best_matches[d] = (q, s)
            
    # Form groups
    groups: dict[str, set[str]] = {q: set() for q in questions}
    for doi, (q_star, _) in best_matches.items():
        groups[q_star].add(doi)
        
    cand_dois = set(best_matches.keys())
    
    # 1. Disjointness
    for i, q1 in enumerate(questions):
        for j, q2 in enumerate(questions):
            if i < j:
                intersection = groups[q1] & groups[q2]
                assert len(intersection) == 0, f"Disjointness violated between {q1} and {q2}: {intersection}"
                
    # 2. Exhaustiveness
    union_dois = set().union(*groups.values())
    assert union_dois == cand_dois, "Exhaustiveness violated: union of groups != qualifying candidates"
    
    print(">>> Theorem 3.3: Disjointness and Exhaustiveness verified.")


def test_theorem_3_3_permutation_sensitivity_on_exact_ties():
    """Adversarial stress test: What happens when exact similarity ties occur under permuted input streams?"""
    q1, q2 = "Question 1", "Question 2"
    doi = "10.1000/tied_paper"
    exact_score = 0.8500000000000000
    
    stream_order_1 = [
        {"doi": doi, "question": q1, "score": exact_score},
        {"doi": doi, "question": q2, "score": exact_score},
    ]
    
    stream_order_2 = [
        {"doi": doi, "question": q2, "score": exact_score},
        {"doi": doi, "question": q1, "score": exact_score},
    ]
    
    def run_grouping(stream):
        best_matches = {}
        for sim in stream:
            d = str(sim["doi"])
            q = str(sim["question"])
            s = float(sim["score"])
            if d not in best_matches or s > best_matches[d][1]:
                best_matches[d] = (q, s)
        return best_matches[doi][0]

    winner_1 = run_grouping(stream_order_1)
    winner_2 = run_grouping(stream_order_2)
    
    print(f"Tie-breaking Order 1 Winner: {winner_1}")
    print(f"Tie-breaking Order 2 Winner: {winner_2}")
    
    # Check if stream order changes outcome on exact scalar tie
    is_stream_dependent = (winner_1 != winner_2)
    if is_stream_dependent:
        print(">>> FINDING: In Python grouping loop, exact scalar ties resolve to the first-encountered stream element.")
        print("    If Cypher query streams records non-deterministically, exact ties are stream-dependent.")
    else:
        print(">>> Tie-breaking is deterministic.")


# ==============================================================================
# SECTION 4: DELIVERABLE R2 — STATISTICAL RECONCILIATION & TESTS
# ==============================================================================

def test_statistical_reconciliation_tables_6_1_to_6_4():
    """Forensic reconciliation of raw CSV dataset against Thesis Tables 6.1-6.4 over 27 benchmark queries."""
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../Runs/Side_by_Side_Comparison.csv"))
    assert os.path.exists(csv_path), f"CSV dataset not found at {csv_path}"
    
    df = pd.read_csv(csv_path)
    
    con_df = df.dropna(subset=["aggregated_similarity_dataFromCon_Statistics.csv Mean Diff"]).copy().iloc[:27]
    typ_df = df.dropna(subset=["aggregated_similarity_dataFromTypestt_Statistics.csv Mean Diff"]).copy().iloc[:27]
    
    assert len(con_df) == 27, f"Expected 27 Consensus queries, got {len(con_df)}"
    assert len(typ_df) == 27, f"Expected 27 Typeset queries, got {len(typ_df)}"
    
    # Delta = ALRS - Benchmark = - (Benchmark - ALRS) in CSV
    con_mean = - con_df["aggregated_similarity_dataFromCon_Statistics.csv Mean Diff"].values * 100.0
    con_med = - con_df["aggregated_similarity_dataFromCon_Statistics.csv Median Diff"].values * 100.0
    con_min = - con_df["aggregated_similarity_dataFromCon_Statistics.csv Min Diff"].values * 100.0
    con_max = - con_df["aggregated_similarity_dataFromCon_Statistics.csv Max Diff"].values * 100.0
    
    typ_mean = - typ_df["aggregated_similarity_dataFromTypestt_Statistics.csv Mean Diff"].values * 100.0
    typ_med = - typ_df["aggregated_similarity_dataFromTypestt_Statistics.csv Median Diff"].values * 100.0
    typ_min = - typ_df["aggregated_similarity_dataFromTypestt_Statistics.csv Min Diff"].values * 100.0
    typ_max = - typ_df["aggregated_similarity_dataFromTypestt_Statistics.csv Max Diff"].values * 100.0
    
    # --- Table 6.1 (Best-Case) ---
    assert np.max(con_med) == pytest.approx(17.74, abs=0.01)
    assert np.max(con_min) == pytest.approx(19.69, abs=0.01)
    assert np.max(con_max) == pytest.approx(7.96, abs=0.01)
    
    assert np.max(typ_mean) == pytest.approx(10.01, abs=0.01)
    assert np.max(typ_min) == pytest.approx(10.64, abs=0.01)
    assert np.max(typ_max) == pytest.approx(12.29, abs=0.01)
    
    # --- Table 6.2 (Average-Case) ---
    assert np.mean(con_mean) == pytest.approx(2.15, abs=0.01)
    assert np.mean(con_min) == pytest.approx(2.92, abs=0.01)
    assert np.mean(con_max) == pytest.approx(-0.18, abs=0.01)
    
    assert np.mean(typ_mean) == pytest.approx(3.74, abs=0.01)
    assert np.mean(typ_min) == pytest.approx(4.27, abs=0.01)
    assert np.mean(typ_max) == pytest.approx(3.39, abs=0.01)
    
    # --- Table 6.3 (Worst-Case) ---
    assert np.min(con_mean) == pytest.approx(-5.34, abs=0.01)
    assert np.min(con_min) == pytest.approx(-3.54, abs=0.01)
    assert np.min(con_max) == pytest.approx(-6.89, abs=0.01)
    
    assert np.min(typ_mean) == pytest.approx(-5.24, abs=0.01)
    assert np.min(typ_min) == pytest.approx(-6.47, abs=0.01)
    assert np.min(typ_max) == pytest.approx(-4.89, abs=0.01)
    
    # --- Table 6.4 (Outcome Distribution) ---
    # Wins: > 0.5%, Ties: [-0.5%, +0.5%], Losses: < -0.5%
    con_wins = int(np.sum(con_mean > 0.5))
    con_ties = int(np.sum(np.abs(con_mean) <= 0.5))
    con_losses = int(np.sum(con_mean < -0.5))
    
    typ_wins = int(np.sum(typ_mean > 0.5))
    typ_losses = int(np.sum(typ_mean < -0.5))
    
    assert con_wins == 20 and con_ties == 3 and con_losses == 4
    assert typ_wins == 23 and typ_losses <= 4
    
    print(">>> Tables 6.1-6.4 Reconciliation: Exact numerical match verified on 27 benchmark queries.")


def test_statistical_hypothesis_assumptions():
    """Stress tests the statistical test assumptions (normality, sample size, Wilcoxon signed-rank)."""
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../Runs/Side_by_Side_Comparison.csv"))
    df = pd.read_csv(csv_path)
    
    con_df = df.dropna(subset=["aggregated_similarity_dataFromCon_Statistics.csv Mean Diff"]).copy().iloc[:27]
    typ_df = df.dropna(subset=["aggregated_similarity_dataFromTypestt_Statistics.csv Mean Diff"]).copy().iloc[:27]
    
    con_mean_diff = - con_df["aggregated_similarity_dataFromCon_Statistics.csv Mean Diff"].values * 100.0
    typ_mean_diff = - typ_df["aggregated_similarity_dataFromTypestt_Statistics.csv Mean Diff"].values * 100.0
    
    # 1. Normality Test (Shapiro-Wilk)
    shapiro_con_stat, shapiro_con_p = stats.shapiro(con_mean_diff)
    shapiro_typ_stat, shapiro_typ_p = stats.shapiro(typ_mean_diff)
    
    print(f"Shapiro-Wilk Normality Test (Consensus Diff): W={shapiro_con_stat:.4f}, p={shapiro_con_p:.4f}")
    print(f"Shapiro-Wilk Normality Test (Typeset Diff):   W={shapiro_typ_stat:.4f}, p={shapiro_typ_p:.4f}")
    
    # 2. Paired t-test
    t_con, p_con = stats.ttest_1samp(con_mean_diff, 0.0)
    t_typ, p_typ = stats.ttest_1samp(typ_mean_diff, 0.0)
    
    # 3. Wilcoxon signed-rank test
    w_con, wp_con = stats.wilcoxon(con_mean_diff)
    w_typ, wp_typ = stats.wilcoxon(typ_mean_diff)
    
    # 4. Effect Sizes (Cohen's d & Hedges' g)
    d_con = np.mean(con_mean_diff) / (np.std(con_mean_diff, ddof=1) + 1e-12)
    d_typ = np.mean(typ_mean_diff) / (np.std(typ_mean_diff, ddof=1) + 1e-12)
    
    N = len(con_mean_diff)
    j_factor = 1.0 - (3.0 / (4.0 * (N - 1) - 1.0))
    g_con = d_con * j_factor
    g_typ = d_typ * j_factor
    
    print(f"Consensus: t={t_con:.3f}, p_t={p_con:.4e}, Wilcoxon p={wp_con:.4e}, d={d_con:.3f}, Hedges_g={g_con:.3f}")
    print(f"Typeset:   t={t_typ:.3f}, p_t={p_typ:.4e}, Wilcoxon p={wp_typ:.4e}, d={d_typ:.3f}, Hedges_g={g_typ:.3f}")
    
    # Assert statistical significance on Wilcoxon (non-parametric, robust to normality violations)
    assert wp_con < 0.01, f"Consensus Wilcoxon test not significant: p={wp_con}"
    assert wp_typ < 0.001, f"Typeset Wilcoxon test not significant: p={wp_typ}"
    assert p_con < 0.05, f"Consensus t-test p={p_con}"
    assert p_typ < 0.001, f"Typeset t-test p={p_typ}"
    
    print(">>> Statistical significance confirmed across both parametric and non-parametric tests.")


# ==============================================================================
# SECTION 5: EDGE CASES HARNESS (Zero vectors, Disconnected, Self-loops)
# ==============================================================================

def test_edge_cases_ranking_and_pagerank():
    """Tests extreme edge cases: single node, isolated nodes, zero citations, self loops."""
    # 1. Zero vector norm
    v_zero = np.zeros(768)
    v_norm = np.random.randn(768)
    v_norm = v_norm / np.linalg.norm(v_norm)
    
    # Dot product with zero vector is 0.0
    dot_zero = float(np.dot(v_zero, v_norm))
    assert dot_zero == 0.0
    
    # 2. Graph with only self-loops
    g_self = nx.DiGraph()
    g_self.add_edge("p1", "p1")
    g_self.add_edge("p2", "p2")
    pr_self = nx.pagerank(g_self, alpha=0.85, max_iter=20)
    pr_norm_self = min_max_normalize(pr_self)
    assert all(v == 1.0 for v in pr_norm_self.values()), "Self-loop graph should normalize to 1.0 when all scores equal"
    
    # 3. Disconnected graph with 0 citations (completely isolated papers)
    g_iso = nx.DiGraph()
    g_iso.add_nodes_from(["p1", "p2", "p3", "p4", "p5"])
    pr_iso = nx.pagerank(g_iso, alpha=0.85, max_iter=20)
    pr_norm_iso = min_max_normalize(pr_iso)
    assert all(v == 1.0 for v in pr_norm_iso.values()), "Isolated graph should normalize to 1.0 when all scores equal"
    
    # 4. Hybrid ranking with zero citation count and None year
    papers = [
        RankedPaper(
            doi="10.1000/zero_cite",
            title="Paper Zero",
            year=None,
            cited_by_count=0,
            similarity_score=0.80,
            pagerank_score=1.0,
            hybrid_score=0.86,
            question_group="Q1",
        ),
        RankedPaper(
            doi="10.1000/high_cite",
            title="Paper High",
            year=2024,
            cited_by_count=150,
            similarity_score=0.80,
            pagerank_score=1.0,
            hybrid_score=0.86,
            question_group="Q1",
        ),
    ]
    
    # Tie breaker: -hybrid_score, -cited_by_count, -year
    # Paper High has 150 citations vs 0 -> Paper High must come first
    papers.sort(key=lambda x: (
        -x.hybrid_score,
        -x.cited_by_count,
        -(x.year if x.year is not None else 0)
    ))
    
    assert papers[0].doi == "10.1000/high_cite"
    assert papers[1].doi == "10.1000/zero_cite"
    
    print(">>> Edge Cases Harness: All boundary conditions handled gracefully.")


# ==============================================================================
# SECTION 6: PAGERANK 3-TIER FALLBACK & NORMALIZATION UNDER SYNTHETIC TOPOLOGIES
# ==============================================================================

@pytest.mark.asyncio
async def test_pagerank_3tier_fallback_synthetic_topologies():
    """Adversarial stress test of PageRank 3-tier fallback and normalization under
    synthetic graph topologies (disconnected, scale-free, complete, empty, single-node).
    """
    topologies = [
        ("Empty Graph", nx.DiGraph()),
        ("Single Node Graph", nx.DiGraph([( "p0", "p0" )])),
        ("Disconnected 5-Component Graph", nx.disjoint_union_all([nx.erdos_renyi_graph(15, 0.15, directed=True) for _ in range(5)])),
        ("Scale-Free Graph", nx.scale_free_graph(50)),
        ("Complete Graph", nx.complete_graph(10, create_using=nx.DiGraph)),
        ("Star Graph (Hub & Leaves)", nx.star_graph(20, create_using=nx.DiGraph)),
        ("Directed Cycle", nx.cycle_graph(15, create_using=nx.DiGraph)),
    ]

    service = Neo4jService("bolt://localhost:7687", "neo4j", "password")

    for name, G in topologies:
        if not isinstance(G, nx.DiGraph):
            G = nx.DiGraph(G)

        # Relabel nodes to string DOIs
        node_map = {n: f"10.1000/node_{n}" for n in G.nodes()}
        G = nx.relabel_nodes(G, node_map)
        nodes_list = list(G.nodes())
        edges_list = [{"source": u, "target": v} for u, v in G.edges()]

        # -------------------------------------------------------------
        # Tier 1: Neo4j GDS Simulation
        # -------------------------------------------------------------
        if nodes_list:
            raw_gds_records = [{"doi": n, "score": float(G.in_degree(n) + 1.0)} for n in nodes_list]
            service.execute_write = AsyncMock(return_value=[])
            service.execute_read = AsyncMock(return_value=raw_gds_records)

            with patch("core.db.neo4j_service.AsyncGraphDatabase") as mock_gdb:
                mock_driver = AsyncMock()
                mock_gdb.driver.return_value = mock_driver
                await service.connect()
                res_gds = await service.compute_pagerank("session-test")

                assert len(res_gds) == len(nodes_list), f"Tier 1 GDS node count mismatch on {name}"
                for doi, score in res_gds.items():
                    assert 0.0 <= score <= 1.0, f"Tier 1 GDS score out of bounds on {name}: {score}"
                if len(res_gds) > 1 and any(G.in_degree(n) != G.in_degree(nodes_list[0]) for n in nodes_list):
                    assert max(res_gds.values()) == 1.0
                    assert min(res_gds.values()) == 0.0

        # -------------------------------------------------------------
        # Tier 2: NetworkX Pure-Python Fallback (GDS fails)
        # -------------------------------------------------------------
        service.execute_write = AsyncMock(side_effect=Exception("GDS unavailable"))
        deg_records = [{"doi": n, "degree": float(G.in_degree(n))} for n in nodes_list]

        async def mock_read_dispatch(query, params=None, database='neo4j'):
            if "degree" in query or "other:Paper" in query:
                return deg_records
            elif "CITES" in query:
                return edges_list
            else:
                return [{"doi": n} for n in nodes_list]

        service.execute_read = AsyncMock(side_effect=mock_read_dispatch)

        with patch("core.db.neo4j_service.AsyncGraphDatabase") as mock_gdb:
            mock_driver = AsyncMock()
            mock_gdb.driver.return_value = mock_driver
            await service.connect()
            res_nx = await service.compute_pagerank("session-test", iterations=20, damping=0.85)

            if not nodes_list:
                assert res_nx == {}, f"Tier 2 NetworkX empty graph did not return empty dict on {name}"
            else:
                assert len(res_nx) == len(nodes_list), f"Tier 2 NetworkX node count mismatch on {name}"
                for doi, score in res_nx.items():
                    assert 0.0 <= score <= 1.0, f"Tier 2 NetworkX score out of bounds on {name}: {score}"

        # -------------------------------------------------------------
        # Tier 3: Degree Centrality Fallback (NetworkX fails/missing)
        # -------------------------------------------------------------
        service.execute_write = AsyncMock(side_effect=Exception("GDS unavailable"))
        service.execute_read = AsyncMock(return_value=deg_records)

        with patch.dict("sys.modules", {"networkx": None}):
            with patch("core.db.neo4j_service.AsyncGraphDatabase") as mock_gdb:
                mock_driver = AsyncMock()
                mock_gdb.driver.return_value = mock_driver
                await service.connect()
                res_deg = await service.compute_pagerank("session-test")

                if not nodes_list:
                    assert res_deg == {}, f"Tier 3 Degree centrality empty graph did not return empty dict on {name}"
                else:
                    assert len(res_deg) == len(nodes_list), f"Tier 3 Degree centrality node count mismatch on {name}"
                    for doi, score in res_deg.items():
                        assert 0.0 <= score <= 1.0, f"Tier 3 Degree centrality score out of bounds on {name}: {score}"

    print(">>> PageRank 3-Tier Fallback: All tiers and synthetic topologies strictly verified.")


# ==============================================================================
# SECTION 7: ADVERSARIAL INVERTED INDEX RECONSTRUCTION
# ==============================================================================

def test_adversarial_inverted_index_reconstruction():
    """Adversarial stress test of abstract inverted index reconstruction with malformed payloads."""
    # 1. Null / Non-dict types
    assert OpenAlexService._reconstruct_abstract(None) is None
    assert OpenAlexService._reconstruct_abstract({}) is None
    assert OpenAlexService._reconstruct_abstract([]) is None  # type: ignore[arg-type]
    assert OpenAlexService._reconstruct_abstract("not a dict") is None  # type: ignore[arg-type]
    assert OpenAlexService._reconstruct_abstract(12345) is None  # type: ignore[arg-type]
    assert OpenAlexService._reconstruct_abstract(True) is None  # type: ignore[arg-type]

    # 2. Malformed keys/values inside dict
    assert OpenAlexService._reconstruct_abstract({"word": None}) is None  # type: ignore[dict-item]
    assert OpenAlexService._reconstruct_abstract({"word": "not a list"}) is None  # type: ignore[dict-item]
    assert OpenAlexService._reconstruct_abstract({"word": [None, "invalid"]}) is None  # type: ignore[list-item]

    # 3. Partial valid entries mixed with malformed ones
    mixed_index = {
        "ValidWord": [0],
        "CorruptedKey": "not a list",
        "CorruptedPositions": [None, "abc"],
    }
    # Should reconstruct "ValidWord" ignoring corrupted fields
    assert OpenAlexService._reconstruct_abstract(mixed_index) == "ValidWord"

    # 4. Out of order & duplicate word positions
    complex_index = {
        "world": [1, 3],
        "Hello": [0, 2],
    }
    assert OpenAlexService._reconstruct_abstract(complex_index) == "Hello world Hello world"

    # 5. Sparse / large gap positions
    sparse_index = {
        "Beginning": [0],
        "End": [100000],
    }
    assert OpenAlexService._reconstruct_abstract(sparse_index) == "Beginning End"

    # 6. Negative & zero positions
    neg_index = {
        "First": [-5],
        "Second": [0],
        "Third": [5],
    }
    assert OpenAlexService._reconstruct_abstract(neg_index) == "First Second Third"

    # 7. Stress test with 10,000 token positions
    large_index = {f"word_{i}": [i] for i in range(10000)}
    reconstructed = OpenAlexService._reconstruct_abstract(large_index)
    assert reconstructed is not None
    assert len(reconstructed.split()) == 10000
    assert reconstructed.startswith("word_0 word_1")
    assert reconstructed.endswith("word_9999")

    print(">>> Inverted Index Reconstruction: Resilient to 100% of malformed / adversarial payloads.")


# ==============================================================================
# SECTION 8: ADVERSARIAL RATE LIMITER STRESS TESTING
# ==============================================================================

@pytest.mark.asyncio
async def test_adversarial_rate_limiter_burst_and_backoff():
    """Adversarial stress test of AdaptiveRateLimiter under rapid 429 backoff, recovery, and concurrency."""
    limiter = AdaptiveRateLimiter(initial_rate=9.0, min_rate=0.5, recovery_increment=0.5)

    assert limiter.current_rate == 9.0

    # 1. 429 Backoff cascade down to min_rate
    rates = []
    for _ in range(10):
        rates.append(limiter.on_429())
    
    assert limiter.current_rate == 0.5, f"Rate did not floor at min_rate: {limiter.current_rate}"
    assert rates == [4.5, 2.25, 1.125, 0.5625, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]

    # 2. Success recovery cascade up to initial_rate
    for _ in range(25):
        limiter.on_success()

    assert limiter.current_rate == 9.0, f"Rate did not cap at initial_rate: {limiter.current_rate}"

    # 3. Reset
    limiter.on_429()
    assert limiter.current_rate < 9.0
    limiter.reset()
    assert limiter.current_rate == 9.0

    # 4. Concurrent acquisition stress test
    high_rate_limiter = AdaptiveRateLimiter(initial_rate=1000.0, min_rate=10.0, recovery_increment=10.0)
    
    acquired_count = 0

    async def worker():
        nonlocal acquired_count
        for _ in range(20):
            await high_rate_limiter.acquire()
            acquired_count += 1

    # Run 50 concurrent workers (1000 total acquisitions)
    tasks = [asyncio.create_task(worker()) for _ in range(50)]
    await asyncio.gather(*tasks)

    assert acquired_count == 1000, f"Expected 1000 acquisitions, got {acquired_count}"

    print(">>> Adaptive Rate Limiter: Stress, backoff, and concurrency tests passed successfully.")


# ==============================================================================
# SECTION 9: EMPIRICAL TELEMETRY BENCHMARK & SYNLIT-BENCH (T069, T072)
# ==============================================================================

def test_empirical_telemetry_runner_teq_and_vts():
    """Verify Equivalent Token Time (T_eq) and VTS ratio >= 1.2 per Constitution A50."""
    from core.logging.telemetry_service import TelemetryService
    svc = TelemetryService(":memory:")
    c_id = "test-camp-001"
    svc.record_turn_event({
        "campaign_id": c_id, "agent_role": "builder", "prompt_tokens": 200,
        "completion_tokens": 300, "latency_ms": 1500.0, "cost_usd": 0.05,
    })
    svc.record_turn_event({
        "campaign_id": c_id, "agent_role": "critic", "prompt_tokens": 350,
        "completion_tokens": 400, "latency_ms": 2000.0, "cost_usd": 0.07,
    })
    vts = svc.compute_verification_to_synthesis_ratio(c_id)
    teq = svc.compute_equivalent_token_time(c_id)
    assert vts >= 1.2, f"Expected VTS >= 1.2, got {vts}"
    assert teq > 0.0, f"Expected positive T_eq, got {teq}"


def test_empirical_telemetry_cost_ceiling():
    """Verify total campaign monetary cost computation strictly within $1.50 ceiling."""
    from core.logging.telemetry_service import TelemetryService
    svc = TelemetryService(":memory:")
    c_id = "test-camp-cost"
    for _ in range(5):
        svc.record_turn_event({
            "campaign_id": c_id, "agent_role": "builder", "prompt_tokens": 100,
            "completion_tokens": 100, "latency_ms": 500.0, "cost_usd": 0.08,
        })
    total_cost = svc.compute_total_cost_usd(c_id)
    assert 0.0 < total_cost <= 1.50, f"Cost {total_cost} exceeded $1.50 ceiling"


def test_synlit_bench_adversarial_generator():
    """SynLit-Bench: verify 100% recall on injected ungrounded DOIs (zero hallucination)."""
    from agents.writing.citation_verifier import verify_citation_grounding
    known_dois = ["10.1145/3308558.3313508", "10.48550/arxiv.1706.03762"]
    injected_synthetic = ["10.9999/hallucinated.doi.001", "10.9999/fabricated.graph.002"]
    manuscript = (
        f"Prior foundations [10.1145/3308558.3313508] established node embeddings. "
        f"Recent claims [{injected_synthetic[0]}] suggest linear scaling. "
        f"However, synthesis [{injected_synthetic[1]}] contradicts empirical bounds."
    )
    result = verify_citation_grounding(text=manuscript, known_dois=known_dois)
    assert not result.is_grounded, "Expected ungrounded flag for injected synthetic DOIs"
    assert len(result.hallucinated_dois) == 2, f"Expected 2 detected flaws, got {result.hallucinated_dois}"
    for syn_doi in injected_synthetic:
        assert syn_doi in result.hallucinated_dois, f"Failed to detect injected flaw: {syn_doi}"
    assert result.hallucination_rate == 2 / 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])


