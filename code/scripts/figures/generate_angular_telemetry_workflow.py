#!/usr/bin/env python3
"""
generate_angular_telemetry_workflow.py
Generates publication-ready vector PDF, 300 DPI PNG, and SVG for:
Figure 6: Angular 21 Reactive Workspace, SVG Hierarchy Tree & Real-Time SSE Telemetry Pipeline.
"""

import os
import subprocess
import sys

def build_dot():
    dot_content = """digraph Angular_Telemetry_Workflow {
    graph [
        rankdir="TB",
        nodesep=0.40,
        ranksep=0.45,
        splines=spline,
        fontname="Helvetica,Arial,sans-serif",
        fontsize=10,
        dpi=300,
        bgcolor="#FFFFFF",
        compound=true,
        pad="0.25,0.25"
    ];

    node [
        fontname="Helvetica,Arial,sans-serif",
        fontsize=9,
        shape=none,
        margin=0
    ];

    edge [
        fontname="Helvetica,Arial,sans-serif",
        fontsize=8,
        color="#334155",
        penwidth=1.4,
        arrowsize=0.75
    ];

    // Header
    header_box [
        label=<
            <table border="1" cellborder="0" cellspacing="0" cellpadding="6" bgcolor="#0F172A" color="#334155" style="rounded">
                <tr>
                    <td align="center" colspan="4">
                        <font color="#FFFFFF" point-size="12"><b>ALRS v2: Angular 21 Reactive Workspace &amp; Real-Time SSE Telemetry Streaming Pipeline</b></font><br/>
                        <font color="#94A3B8" point-size="9">Interactive Hierarchy Tree | Dynamic Model Tier Management | Live FastAPI EventSource Streaming</font>
                    </td>
                </tr>
            </table>
        >
    ];

    // Frontend Layer
    subgraph cluster_frontend {
        graph [
            label=<<table border="0" cellborder="0"><tr><td><font color="#DC2626" point-size="11"><b>ANGULAR 21 REACTIVE FRONTEND CLIENT (/agents, /projects/:id)</b></font></td></tr></table>>,
            style="rounded,filled",
            fillcolor="#FEF2F2",
            color="#EF4444",
            penwidth=1.3,
            margin=8
        ];

        subgraph frontend_components {
            graph [rank="same"];

            Workspace_Tabs [
                label=<
                    <table border="2" cellborder="0" cellspacing="0" cellpadding="5" bgcolor="#FFFFFF" color="#DC2626" style="rounded">
                        <tr><td bgcolor="#DC2626" align="center"><font color="#FFFFFF" point-size="9"><b>5-Stage Reactive Workspace Tabs</b></font></td></tr>
                        <tr><td bgcolor="#FEE2E2" align="center"><font color="#991B1B" point-size="8">Signals &amp; Standalone Components</font></td></tr>
                        <tr>
                            <td align="left" cellpadding="4">
                                <font color="#334155" point-size="8">
                                • [Research Tab] Search, crawl queue, BFS graph<br/>
                                • [Analysis Tab] Matrix extraction &amp; gap radar<br/>
                                • [Planning Tab] Outline blueprint editor<br/>
                                • [Writing Tab] Split markdown &amp; review stream<br/>
                                • [Export Tab] LaTeX preview &amp; PDF download
                                </font>
                            </td>
                        </tr>
                    </table>
                >
            ];

            Tree_Component [
                label=<
                    <table border="2" cellborder="0" cellspacing="0" cellpadding="5" bgcolor="#FFFFFF" color="#DC2626" style="rounded">
                        <tr><td bgcolor="#DC2626" align="center"><font color="#FFFFFF" point-size="9"><b>HierarchyTreeComponent</b></font></td></tr>
                        <tr><td bgcolor="#FEE2E2" align="center"><font color="#991B1B" point-size="8">Interactive SVG Tree &amp; Drawer</font></td></tr>
                        <tr>
                            <td align="left" cellpadding="4">
                                <font color="#334155" point-size="8">
                                • SVG quadratic Bézier delegation curves<br/>
                                • Tier badges (T1/T2) &amp; status indicators<br/>
                                • Click node: Opens Agent Config Drawer<br/>
                                • Collapsible sub-swarm branches
                                </font>
                            </td>
                        </tr>
                    </table>
                >
            ];

            Tier_Editor [
                label=<
                    <table border="2" cellborder="0" cellspacing="0" cellpadding="5" bgcolor="#FFFFFF" color="#DC2626" style="rounded">
                        <tr><td bgcolor="#DC2626" align="center"><font color="#FFFFFF" point-size="9"><b>TierManagementService &amp; Modal</b></font></td></tr>
                        <tr><td bgcolor="#FEE2E2" align="center"><font color="#991B1B" point-size="8">Dynamic Model Tier Editor</font></td></tr>
                        <tr>
                            <td align="left" cellpadding="4">
                                <font color="#334155" point-size="8">
                                • CRUD custom tiers (T1, T2, T3, Custom)<br/>
                                • Sampling sliders: Temperature, Top-p<br/>
                                • Mode Toggle: Inherit vs Custom Override<br/>
                                • Instant cascading parameter sync
                                </font>
                            </td>
                        </tr>
                    </table>
                >
            ];
        }
    }

    // Communication Layer (SSE & REST)
    subgraph cluster_comm {
        graph [
            label=<<table border="0" cellborder="0"><tr><td><font color="#4F46E5" point-size="11"><b>REAL-TIME TRANSPORT &amp; EVENTSTREAM PROTOCOL</b></font></td></tr></table>>,
            labelloc="b",
            style="rounded,filled",
            fillcolor="#EEF2FF",
            color="#6366F1",
            penwidth=1.3,
            margin=8
        ];

        SSE_Bus [
            label=<
                <table border="2" cellborder="0" cellspacing="0" cellpadding="5" bgcolor="#FFFFFF" color="#4F46E5" style="rounded">
                    <tr><td bgcolor="#4F46E5" align="center"><font color="#FFFFFF" point-size="9"><b>FastAPI Server-Sent Events (SSE) Engine (/api/events)</b></font></td></tr>
                    <tr>
                        <td align="left" cellpadding="4">
                            <font color="#334155" point-size="8">
                            • <b>Event Types:</b> <font face="Courier">agent_start, thought_delta, tool_call, tool_result, draft_chunk, review_verdict, error_alert</font><br/>
                            • <b>Transport:</b> Standard HTTP/2 EventSource streaming with automatic reconnection &amp; heartbeat pings<br/>
                            • <b>Telemetry Payload:</b> Token consumption counters, model latency timers, active stage transition triggers
                            </font>
                        </td>
                    </tr>
                </table>
            >
        ];
    }

    // Backend Execution Layer
    subgraph cluster_backend {
        graph [
            label=<<table border="0" cellborder="0"><tr><td><font color="#065F46" point-size="11"><b>BACKEND FASTAPI &amp; GOOGLE ADK EXECUTION RUNTIME</b></font></td></tr></table>>,
            style="rounded,filled",
            fillcolor="#ECFDF5",
            color="#10B981",
            penwidth=1.3,
            margin=8
        ];

        subgraph backend_services {
            graph [rank="same"];

            ADK_Runner [
                label=<
                    <table border="2" cellborder="0" cellspacing="0" cellpadding="5" bgcolor="#FFFFFF" color="#059669" style="rounded">
                        <tr><td bgcolor="#059669" align="center"><font color="#FFFFFF" point-size="9"><b>ADK Swarm Execution Engine</b></font></td></tr>
                        <tr>
                            <td align="left" cellpadding="4">
                                <font color="#334155" point-size="8">
                                • Async multi-agent delegation loop<br/>
                                • ToolContext state mutation hooks<br/>
                                • Pre-model state hydration filter
                                </font>
                            </td>
                        </tr>
                    </table>
                >
            ];

            Persistence_Layer [
                label=<
                    <table border="2" cellborder="0" cellspacing="0" cellpadding="5" bgcolor="#FFFFFF" color="#059669" style="rounded">
                        <tr><td bgcolor="#059669" align="center"><font color="#FFFFFF" point-size="9"><b>Dual Storage &amp; GraphRAG</b></font></td></tr>
                        <tr>
                            <td align="left" cellpadding="4">
                                <font color="#334155" point-size="8">
                                • Atomic Disk JSON + MySQL Audit<br/>
                                • Neo4j Epistemic Knowledge Graph<br/>
                                • Deterministic BibTeX / PDF Generator
                                </font>
                            </td>
                        </tr>
                    </table>
                >
            ];
        }
    }

    // Connections
    header_box -> Tree_Component [style="invis"];

    Workspace_Tabs -> SSE_Bus [penwidth=1.6, color="#4F46E5", label=" EventSource Listen "];
    Tree_Component -> SSE_Bus [penwidth=1.6, color="#4F46E5", label=" Agent State Updates "];
    Tier_Editor    -> SSE_Bus [penwidth=1.6, color="#4F46E5", label=" REST Tier Config "];

    SSE_Bus -> ADK_Runner [penwidth=1.8, color="#059669", label=" Dispatches Tasks "];
    ADK_Runner -> SSE_Bus [penwidth=1.8, color="#4F46E5", label=" Streams Deltas "];

    ADK_Runner -> Persistence_Layer [penwidth=1.8, color="#059669", label=" State &amp; Graph Writes "];
}
"""
    return dot_content

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dot_content = build_dot()
    
    dot_file = os.path.join(script_dir, "angular_telemetry_workflow.dot")
    pdf_file = os.path.join(script_dir, "angular_telemetry_workflow.pdf")
    png_file = os.path.join(script_dir, "angular_telemetry_workflow.png")
    svg_file = os.path.join(script_dir, "angular_telemetry_workflow.svg")

    with open(dot_file, "w") as f:
        f.write(dot_content)
    print(f"Wrote {dot_file}")

    cmd_pdf = ["dot", "-Tpdf", dot_file, "-o", pdf_file]
    cmd_png = ["dot", "-Tpng", "-Gdpi=300", dot_file, "-o", png_file]
    cmd_svg = ["dot", "-Tsvg", dot_file, "-o", svg_file]

    for cmd in [cmd_pdf, cmd_png, cmd_svg]:
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"Error executing {' '.join(cmd)}:\n{res.stderr}", file=sys.stderr)
            sys.exit(1)

    print(f"Successfully generated:")
    print(f"  - {pdf_file} ({os.path.getsize(pdf_file)} bytes)")
    print(f"  - {png_file} ({os.path.getsize(png_file)} bytes)")
    print(f"  - {svg_file} ({os.path.getsize(svg_file)} bytes)")

if __name__ == "__main__":
    main()
