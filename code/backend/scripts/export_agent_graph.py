"""Generate visual Agent Swarm & Tool Graph in Mermaid, DOT, and HTML formats."""
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.agent import root_agent

def generate_mermaid(agent) -> str:
    lines = [
        "graph TB",
        "  %% Styling Definitions",
        "  classDef orchestrator fill:#4f46e5,stroke:#818cf8,stroke-width:2px,color:#ffffff,font-weight:bold;",
        "  classDef swarm fill:#2563eb,stroke:#60a5fa,stroke-width:2px,color:#ffffff,font-weight:bold;",
        "  classDef specialist fill:#0d9488,stroke:#2dd4bf,stroke-width:2px,color:#ffffff,font-weight:bold;",
        "  classDef loop fill:#d97706,stroke:#fbbf24,stroke-width:2px,color:#ffffff,font-weight:bold;",
        "  classDef tool fill:#1e293b,stroke:#475569,stroke-width:1px,color:#38bdf8,font-size:12px;",
        ""
    ]

    edges = []
    nodes = []

    def walk(a, parent_id=None):
        name = getattr(a, 'name', a.__class__.__name__)
        node_id = name.replace(" ", "_")
        tools = getattr(a, 'tools', [])
        sub_agents = getattr(a, 'sub_agents', [])

        # Assign class
        if node_id == "ProjectAgent":
            cls = "orchestrator"
            icon = "👑 "
        elif node_id in ["ResearchAgent", "PlannerAgent", "WriterAgent"]:
            cls = "swarm"
            icon = "🔬 " if "Research" in node_id else ("📐 " if "Planner" in node_id else "✍️ ")
        elif "Loop" in node_id:
            cls = "loop"
            icon = "🔄 "
        else:
            cls = "specialist"
            icon = "🤖 "

        nodes.append(f'  {node_id}["{icon}<b>{name}</b>"]:::{cls}')

        if parent_id:
            edges.append(f"  {parent_id} -->|delegates to| {node_id}")

        for i, t in enumerate(tools):
            tname = getattr(t, '__name__', str(t))
            tid = f"{node_id}_t_{i}"
            nodes.append(f'  {tid}["🔧 {tname}"]:::tool')
            edges.append(f"  {node_id} -.->|tool| {tid}")

        for sub in sub_agents:
            walk(sub, node_id)

    walk(root_agent)

    lines.extend(nodes)
    lines.append("")
    lines.extend(edges)
    return "\n".join(lines)

def main():
    mmd = generate_mermaid(root_agent)
    
    out_dir = Path(__file__).resolve().parent.parent / "docs"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    mmd_file = out_dir / "agent_hierarchy_tools.mmd"
    with open(mmd_file, "w") as f:
        f.write(mmd)
    print(f"Generated Mermaid graph at: {mmd_file}")

    # Generate standalone HTML preview
    html_file = out_dir / "agent_hierarchy_tools.html"
    html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>ALRS v2 / GraphSelect — Agent Swarm & Tools Architecture</title>
  <script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
  <script>mermaid.initialize({{startOnLoad:true, theme: 'dark'}});</script>
  <style>
    body {{ background: #0f172a; color: #f8fafc; font-family: sans-serif; padding: 2rem; }}
    h1 {{ text-align: center; color: #60a5fa; }}
    .mermaid {{ display: flex; justify-content: center; margin-top: 2rem; }}
  </style>
</head>
<body>
  <h1>ALRS v2 Google ADK Agent Swarm & Tools Hierarchy</h1>
  <div class="mermaid">
{mmd}
  </div>
</body>
</html>"""
    with open(html_file, "w") as f:
        f.write(html_content)
    print(f"Generated Interactive HTML at: {html_file}")

if __name__ == "__main__":
    main()
