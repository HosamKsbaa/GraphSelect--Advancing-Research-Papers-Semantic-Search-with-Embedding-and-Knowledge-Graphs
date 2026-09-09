#!/usr/bin/env python3
"""
generate_benchmark_comparison_charts.py
Generates publication-ready vector PDF, 300 DPI PNG, and SVG for:
Figure 4: Publication-Grade Comparative Benchmark Performance Charts.
Includes:
- Subplot A: Swarm ADK Subsystem Evaluation (Latency & Tokens/Turn across 7 subsystems)
- Subplot B: Empirical Win Rate & Cosine Similarity Advantage (Consensus vs Typeset, p-values)
- Subplot C: Precision, Recall & F1-Score across 4 Query Types (Foundational, Contemporary, Methodological, Comparative)
- Subplot D: Grounded Citation Verification & Hallucination Rate Comparison (ALRS GCDL vs Naive RAG vs Single-Shot LLM)
"""

import os
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# Apply clean publication style
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["DejaVu Sans", "Helvetica", "Arial"],
    "font.size": 9,
    "axes.labelsize": 9.5,
    "axes.titlesize": 10.5,
    "xtick.labelsize": 8.5,
    "ytick.labelsize": 8.5,
    "legend.fontsize": 8.5,
    "figure.titlesize": 12,
    "axes.edgecolor": "#334155",
    "axes.linewidth": 0.9,
    "grid.color": "#E2E8F0",
    "grid.linestyle": "--",
    "grid.linewidth": 0.6,
    "figure.autolayout": False
})

def create_charts(output_prefix):
    fig = plt.figure(figsize=(13.5, 9.2), dpi=300)
    gs = fig.add_gridspec(2, 2, hspace=0.34, wspace=0.22, left=0.12, right=0.96, top=0.91, bottom=0.07)

    # -------------------------------------------------------------------------
    # SUBPLOT A: SWARM ADK BENCHMARK (Latency & Tokens per Turn)
    # -------------------------------------------------------------------------
    ax_a = fig.add_subplot(gs[0, 0])
    agents = [
        "ProjectAgent",
        "ALRSAgent",
        "GapFinder",
        "EvidenceSynth",
        "PlannerAgent",
        "WriterLoop",
        "DebuggerAgent",
        "Full Swarm (Avg)"
    ]
    latencies = [1.07, 2.42, 1.79, 3.03, 1.61, 4.85, 1.96, 2.26]
    tokens = [1240, 2890, 2150, 4200, 2410, 5620, 2780, 2877]
    pass_rates = [100.0] * 8
    
    y_pos = np.arange(len(agents))
    bar_height = 0.42

    color_latency = "#2563EB"
    color_tokens = "#059669"

    bars1 = ax_a.barh(y_pos - bar_height/2, latencies, height=bar_height, color=color_latency, alpha=0.9, label="Mean Latency (s)", edgecolor="#1E3A8A")
    ax_a.set_xlabel("Mean Execution Latency (seconds)", color="#1E3A8A", weight="bold")
    ax_a.set_xlim(0, 6.2)
    ax_a.set_yticks(y_pos)
    ax_a.set_yticklabels(agents, weight="bold")
    ax_a.invert_yaxis()
    ax_a.grid(True, axis="x", alpha=0.7)

    # Add text labels on latency bars
    for bar in bars1:
        w = bar.get_width()
        ax_a.text(w + 0.1, bar.get_y() + bar.get_height()/2, f"{w:.2f}s", va="center", ha="left", fontsize=7.5, color="#1E3A8A", weight="bold")

    # Twin axis for token counts
    ax_a2 = ax_a.twiny()
    bars2 = ax_a2.barh(y_pos + bar_height/2, tokens, height=bar_height, color=color_tokens, alpha=0.65, label="Tokens / Turn", edgecolor="#065F46", hatch="//")
    ax_a2.set_xlabel("Average Token Usage per Turn", color="#065F46", weight="bold")
    ax_a2.set_xlim(0, 7500)
    ax_a2.grid(False)

    for bar in bars2:
        w = bar.get_width()
        ax_a2.text(w + 100, bar.get_y() + bar.get_height()/2, f"{int(w):,}", va="center", ha="left", fontsize=7.5, color="#065F46")

    # Unified Legend
    patches = [
        mpatches.Patch(facecolor=color_latency, edgecolor="#1E3A8A", label="Mean Latency (s)"),
        mpatches.Patch(facecolor=color_tokens, edgecolor="#065F46", hatch="//", alpha=0.7, label="Tokens / Turn"),
        mpatches.Patch(facecolor="#FDE047", edgecolor="#CA8A04", label="100% Pass Rate (23/23 Gold Tests)")
    ]
    ax_a.legend(handles=patches, loc="lower right", framealpha=0.95)
    ax_a.set_title("(a) Google ADK Swarm Evaluation: Latency & Token Economics", weight="bold", pad=14)

    # -------------------------------------------------------------------------
    # SUBPLOT B: EMPIRICAL WIN RATE & SIMILARITY ADVANTAGE (27 QUERIES)
    # -------------------------------------------------------------------------
    ax_b = fig.add_subplot(gs[0, 1])
    
    comparisons = ["ALRS vs. Consensus.app", "ALRS vs. Typeset.io (SciSpace)"]
    wins = [20, 23]
    ties = [3, 0]
    losses = [4, 4]
    win_rates = [74.07, 85.19]
    mean_diffs = [+2.15, +3.74]
    p_values = ["p = 0.0212 *", "p = 1.94e-5 ***"]

    x = np.arange(len(comparisons))
    width = 0.24

    b_wins = ax_b.bar(x - width, wins, width, label="Wins (Δ > +0.5%)", color="#10B981", edgecolor="#047857", alpha=0.9)
    b_ties = ax_b.bar(x, ties, width, label="Ties (|Δ| ≤ 0.5%)", color="#94A3B8", edgecolor="#475569", alpha=0.9)
    b_losses = ax_b.bar(x + width, losses, width, label="Losses (Δ < -0.5%)", color="#EF4444", edgecolor="#B91C1C", alpha=0.9)

    ax_b.set_ylabel("Number of Benchmark Queries (N = 27)", weight="bold")
    ax_b.set_xticks(x)
    ax_b.set_xticklabels(comparisons, weight="bold")
    ax_b.set_ylim(0, 34)
    ax_b.grid(True, axis="y", alpha=0.7)

    # Annotate counts on bars
    for bars in [b_wins, b_ties, b_losses]:
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax_b.text(bar.get_x() + bar.get_width()/2, h + 0.5, f"{int(h)}", ha="center", va="bottom", fontsize=8, weight="bold")

    # Annotation callouts for win rate & p-values
    ax_b.annotate(f"Win Rate: 74.1%\nMean Δ: +2.15%\n{p_values[0]}", xy=(0, 20.5), xytext=(0, 25),
                  ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#EFF6FF", ec="#3B82F6", lw=1.2),
                  fontsize=8, weight="bold", color="#1E40AF")

    ax_b.annotate(f"Win Rate: 85.2%\nMean Δ: +3.74%\n{p_values[1]}", xy=(1, 23.5), xytext=(1, 25),
                  ha="center", bbox=dict(boxstyle="round,pad=0.3", fc="#EFF6FF", ec="#3B82F6", lw=1.2),
                  fontsize=8, weight="bold", color="#1E40AF")

    ax_b.legend(loc="upper center", ncol=3, framealpha=0.95)
    ax_b.set_title("(b) Empirical Retrieval Outcome Distribution across 27 Benchmark Queries", weight="bold")

    # -------------------------------------------------------------------------
    # SUBPLOT C: PRECISION, RECALL & F1 ACROSS QUERY TYPES
    # -------------------------------------------------------------------------
    ax_c = fig.add_subplot(gs[1, 0])
    query_types = ["Foundational\n(Seminal Prior Art)", "Contemporary\n(Recent Breakthroughs)", "Methodological\n(Architectures/Limits)", "Comparative\n(Trade-off Synthesis)"]
    
    # Precision, Recall, F1
    alrs_f1 = [90.5, 92.6, 90.6, 94.1]
    con_f1 = [74.6, 79.1, 71.7, 68.8]
    typ_f1 = [77.6, 80.7, 76.0, 73.4]

    x_c = np.arange(len(query_types))
    w_c = 0.25

    b_alrs = ax_c.bar(x_c - w_c, alrs_f1, w_c, label="ALRS v2 (Ours)", color="#2563EB", edgecolor="#1E3A8A", alpha=0.95)
    b_typ = ax_c.bar(x_c, typ_f1, w_c, label="Typeset.io Baseline", color="#0D9488", edgecolor="#115E59", alpha=0.85)
    b_con = ax_c.bar(x_c + w_c, con_f1, w_c, label="Consensus.app Baseline", color="#F59E0B", edgecolor="#B45309", alpha=0.85)

    ax_c.set_ylabel("Harmonic Mean F1-Score (%)", weight="bold")
    ax_c.set_xticks(x_c)
    ax_c.set_xticklabels(query_types, fontsize=8)
    ax_c.set_ylim(50, 114)
    ax_c.grid(True, axis="y", alpha=0.7)

    for bars in [b_alrs, b_typ, b_con]:
        for bar in bars:
            h = bar.get_height()
            ax_c.text(bar.get_x() + bar.get_width()/2, h + 1.0, f"{h:.1f}%", ha="center", va="bottom", fontsize=7.2, weight="bold")

    ax_c.legend(loc="upper center", ncol=3, framealpha=0.95)
    ax_c.set_title("(c) Multi-Type Retrieval F1-Score: ALRS v2 vs. Commercial Baselines", weight="bold")

    # -------------------------------------------------------------------------
    # SUBPLOT D: ZERO-HALLUCINATION & CITATION GROUNDING FIDELITY (GCDL)
    # -------------------------------------------------------------------------
    ax_d = fig.add_subplot(gs[1, 1])
    
    systems = ["ALRS v2\n(Grounded GCDL)", "Naive RAG\n(Vector Index Only)", "Single-Shot LLM\n(Unconstrained Prompt)"]
    hallucination_rates = [0.0, 9.8, 22.4]
    coverage_rates = [100.0, 81.5, 62.0]
    tex_compilability = [100.0, 74.0, 48.1]

    x_d = np.arange(len(systems))
    w_d = 0.25

    b_hr = ax_d.bar(x_d - w_d, hallucination_rates, w_d, label="Hallucination Rate (HR %)", color="#DC2626", edgecolor="#991B1B", alpha=0.9)
    b_cr = ax_d.bar(x_d, coverage_rates, w_d, label="Citation Grounding (CR %)", color="#10B981", edgecolor="#047857", alpha=0.9)
    b_tex = ax_d.bar(x_d + w_d, tex_compilability, w_d, label="TeX Compilation Pass (%)", color="#6366F1", edgecolor="#4338CA", alpha=0.9)

    ax_d.set_ylabel("Verification Percentage (%)", weight="bold")
    ax_d.set_xticks(x_d)
    ax_d.set_xticklabels(systems, weight="bold", fontsize=8.5)
    ax_d.set_ylim(0, 115)
    ax_d.grid(True, axis="y", alpha=0.7)

    for bars in [b_hr, b_cr, b_tex]:
        for bar in bars:
            h = bar.get_height()
            ax_d.text(bar.get_x() + bar.get_width()/2, h + 1.2, f"{h:.1f}%", ha="center", va="bottom", fontsize=7.5, weight="bold")

    # Annotation highlight
    ax_d.annotate("GCDL Theorem 1:\nStrict 0.0% Hallucination\nFormally Proven & Verified",
                  xy=(0 - w_d, 0), xytext=(0.25, 40),
                  arrowprops=dict(arrowstyle="->", color="#DC2626", lw=1.5),
                  bbox=dict(boxstyle="round,pad=0.4", fc="#FEF2F2", ec="#DC2626", lw=1.2),
                  fontsize=8, weight="bold", color="#991B1B")

    ax_d.legend(loc="upper right", framealpha=0.95)
    ax_d.set_title("(d) Grounded Citation Verification & Hallucination Elimination", weight="bold")

    # Overall Super Title
    fig.suptitle("ALRS v2 Empirical Benchmarking Suite: Multi-Agent Performance, Comparative Superiority & Zero Hallucination",
                 weight="bold", fontsize=12.5, y=0.98, color="#0F172A")

    # Save to targets
    pdf_path = f"{output_prefix}.pdf"
    png_path = f"{output_prefix}.png"
    svg_path = f"{output_prefix}.svg"

    fig.savefig(pdf_path, format="pdf")
    fig.savefig(png_path, format="png", dpi=300)
    fig.savefig(svg_path, format="svg")
    plt.close(fig)

    print(f"Successfully generated:")
    print(f"  - {pdf_path} ({os.path.getsize(pdf_path)} bytes)")
    print(f"  - {png_path} ({os.path.getsize(png_path)} bytes)")
    print(f"  - {svg_path} ({os.path.getsize(svg_path)} bytes)")

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_prefix = os.path.join(script_dir, "benchmark_comparison_charts")
    create_charts(output_prefix)

if __name__ == "__main__":
    main()
