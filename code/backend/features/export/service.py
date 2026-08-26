"""Export service for publication-ready outputs in ALRS v2.

Extracted business logic for BibTeX generation, LaTeX conversion,
and citation graph export.  Used by both ADK tool wrappers and
FastAPI router endpoints.

Functions:
    - export_bibtex: Generate a .bib file from project papers
    - export_latex: Convert Markdown drafts into a LaTeX document
    - export_citation_graph: Export citation network as JSON + GraphML
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.db.neo4j_service import Neo4jService
    from core.logging.log_service import LogService

logger = logging.getLogger(__name__)


def _generate_graphml(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    """Generate a standard GraphML XML string from nodes and edges."""
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns"',
        '         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"',
        '         xsi:schemaLocation="http://graphml.graphdrawing.org/xmlns http://graphml.graphdrawing.org/xmlns/1.0/graphml.xsd">',
        '  <key id="title" for="node" attr.name="title" attr.type="string"/>',
        '  <key id="year" for="node" attr.name="year" attr.type="int"/>',
        '  <key id="citations" for="node" attr.name="citations" attr.type="int"/>',
        '  <graph id="G" edgedefault="directed">',
    ]

    for n in nodes:
        node_id = n["id"]
        title_esc = n["title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
        xml.append(f'    <node id="{node_id}">')
        xml.append(f'      <data key="title">{title_esc}</data>')
        xml.append(f'      <data key="year">{n["year"]}</data>')
        xml.append(f'      <data key="citations">{n["citations"]}</data>')
        xml.append('    </node>')

    for idx, e in enumerate(edges):
        xml.append(f'    <edge id="e{idx}" source="{e["source"]}" target="{e["target"]}"/>')

    xml.append('  </graph>')
    xml.append('</graphml>')
    return "\n".join(xml)


class ExportService:
    """Export service for publication-ready outputs.

    Attributes:
        _neo4j: Injected Neo4j graph database service.
        _log_service: Optional logging service for telemetry.
        _projects_dir: Root directory for per-project artifacts.
    """

    def __init__(
        self,
        neo4j: Neo4jService,
        log_service: LogService | None = None,
        projects_dir: str = "projects",
    ) -> None:
        self._neo4j = neo4j
        self._log_service = log_service
        self._projects_dir = projects_dir

    # ------------------------------------------------------------------
    # T047 – export_bibtex
    # ------------------------------------------------------------------

    async def export_bibtex(
        self,
        project_id: str,
    ) -> dict[str, Any]:
        """Export the project's paper library as a BibTeX file.

        Queries Neo4j for all papers linked to the project and formats
        them as BibTeX entries.  The resulting ``.bib`` file is saved to
        ``{projects_dir}/{project_id}/exports/references.bib``.

        Args:
            project_id: The project UUID.

        Returns:
            A dict with keys: entry_count, saved_path, bibtex_preview.
        """
        from agents.writing.tex_formatter import generate_bibtex

        neo4j = self._neo4j

        # Fetch all project papers
        papers = await neo4j.get_project_papers(project_id, limit=500)
        if not papers:
            return {"entry_count": 0, "message": "No papers in the project to export."}

        # Generate BibTeX content
        bibtex_content: str = generate_bibtex(papers)

        # Save to disk
        export_dir = Path(self._projects_dir) / project_id / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        bib_path = export_dir / "references.bib"
        bib_path.write_text(bibtex_content, encoding="utf-8")

        # Log
        if self._log_service:
            await self._log_service.log_agent_trace(
                project_id=project_id,
                agent_name="WriterAgent",
                event_type="tool_call",
                details={
                    "tool": "export_bibtex",
                    "entry_count": len(papers),
                    "path": str(bib_path),
                },
            )

        return {
            "entry_count": len(papers),
            "saved_path": str(bib_path),
            "bibtex_preview": bibtex_content[:500],
        }

    # ------------------------------------------------------------------
    # T048 – export_latex
    # ------------------------------------------------------------------

    async def export_latex(
        self,
        project_id: str,
        template: str = "ieee",
    ) -> dict[str, Any]:
        """Convert approved Markdown draft sections into a LaTeX document.

        Reads all ``.md`` files from ``{projects_dir}/{project_id}/drafts/``,
        converts them to LaTeX using the specified template, generates
        a companion ``.bib`` file, and saves both to
        ``{projects_dir}/{project_id}/exports/``.

        Args:
            project_id: The project UUID.
            template: LaTeX template style — 'ieee', 'acm', or 'plain'.

        Returns:
            A dict with keys: template, section_count, tex_path, bib_path,
            and a short preview of the LaTeX output.
        """
        from agents.writing.tex_formatter import format_to_latex, generate_bibtex

        neo4j = self._neo4j
        project_dir = Path(self._projects_dir) / project_id

        # Read all draft files
        drafts_dir = project_dir / "drafts"
        if not drafts_dir.exists():
            return {"error": "No drafts directory found. Draft sections first."}

        md_files = sorted(drafts_dir.glob("*.md"))
        if not md_files:
            return {"error": "No Markdown draft files found in drafts/."}

        # Collect all Markdown content
        sections_md: list[str] = []
        for md_file in md_files:
            content = md_file.read_text(encoding="utf-8")
            sections_md.append(content)

        combined_markdown = "\n\n".join(sections_md)

        # Collect all DOI citations from the Markdown
        doi_pattern = re.compile(r"10\.\d{4,9}/[^\s,)}\]]+")
        found_dois: list[str] = list(set(doi_pattern.findall(combined_markdown)))

        # Fetch paper data for BibTeX generation
        papers = await neo4j.get_project_papers(project_id, limit=500)

        # Generate BibTeX
        bibtex_content: str = generate_bibtex(papers)

        # Generate LaTeX
        latex_content: str = format_to_latex(
            markdown_content=combined_markdown,
            citations=found_dois,
            template=template,
        )

        # Save outputs
        export_dir = project_dir / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)

        tex_path = export_dir / "literature_review.tex"
        tex_path.write_text(latex_content, encoding="utf-8")

        bib_path = export_dir / "references.bib"
        bib_path.write_text(bibtex_content, encoding="utf-8")

        # Log
        if self._log_service:
            await self._log_service.log_agent_trace(
                project_id=project_id,
                agent_name="WriterAgent",
                event_type="tool_call",
                details={
                    "tool": "export_latex",
                    "template": template,
                    "section_count": len(md_files),
                    "tex_path": str(tex_path),
                },
            )

        return {
            "template": template,
            "section_count": len(md_files),
            "tex_path": str(tex_path),
            "bib_path": str(bib_path),
            "latex_preview": latex_content[:600],
        }

    # ------------------------------------------------------------------
    # T049 – export_citation_graph
    # ------------------------------------------------------------------

    async def export_citation_graph(
        self,
        project_id: str,
    ) -> dict[str, Any]:
        """Export the project's paper library citation network.

        Queries Neo4j for all papers in the project and their internal
        citation relationships.  Generates both a standard JSON node-link
        representation and a GraphML XML file (compatible with Gephi),
        saving them in the project exports directory.

        Args:
            project_id: The project UUID.

        Returns:
            A dict with keys: node_count, edge_count, json_path, graphml_path.
        """
        neo4j = self._neo4j

        try:
            # 1. Fetch all nodes using dedicated method
            node_records = await neo4j.get_citation_graph_nodes(project_id)
            if not node_records:
                return {"node_count": 0, "edge_count": 0, "message": "No papers in the project to export."}

            nodes = [
                {
                    "id": str(r["doi"]),
                    "title": str(r.get("title", "")),
                    "year": int(r.get("year", 0)) if r.get("year") is not None else 0,
                    "citations": int(r.get("cited_by_count", 0)) if r.get("cited_by_count") is not None else 0,
                }
                for r in node_records
                if r.get("doi")
            ]

            # 2. Fetch all edges using dedicated method
            edge_records = await neo4j.get_citation_graph_edges(project_id)
            edges = [
                {
                    "source": str(r["source"]),
                    "target": str(r["target"]),
                }
                for r in edge_records
                if r.get("source") and r.get("target")
            ]

            # 3. Format JSON and GraphML
            json_content = json.dumps({"nodes": nodes, "links": edges}, indent=2)
            graphml_content = _generate_graphml(nodes, edges)

            # 4. Save to disk
            export_dir = Path(self._projects_dir) / project_id / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)

            json_path = export_dir / "citation_graph.json"
            json_path.write_text(json_content, encoding="utf-8")

            graphml_path = export_dir / "citation_graph.graphml"
            graphml_path.write_text(graphml_content, encoding="utf-8")

            # 5. Log trace
            if self._log_service:
                await self._log_service.log_agent_trace(
                    project_id=project_id,
                    agent_name="WriterAgent",
                    event_type="tool_call",
                    details={
                        "tool": "export_citation_graph",
                        "node_count": len(nodes),
                        "edge_count": len(edges),
                        "json_path": str(json_path),
                        "graphml_path": str(graphml_path),
                    },
                )

            return {
                "node_count": len(nodes),
                "edge_count": len(edges),
                "json_path": str(json_path),
                "graphml_path": str(graphml_path),
            }

        except Exception as exc:
            logger.error("export_citation_graph failed: %s", exc)
            return {"error": str(exc), "node_count": 0, "edge_count": 0}

    # ------------------------------------------------------------------
    # Automated PDF Compilation – compile_pdf
    # ------------------------------------------------------------------

    async def compile_pdf(
        self,
        project_id: str,
        template: str = "plain",
        timeout_sec: int = 30,
    ) -> Path:
        """Compile project LaTeX drafts and citations into a publication-ready PDF.

        1. Generates LaTeX document and BibTeX bibliography via ``export_latex``.
        2. Copies custom template class files (IEEEtran.cls, acmart.cls) into the compilation environment.
        3. Executes pdflatex safely with timeout enforcement.
        4. Validates output PDF existence and non-zero size.
        5. Saves final PDF artifact to ``{projects_dir}/{project_id}/exports/literature_review.pdf``.

        Args:
            project_id: The project UUID.
            template: LaTeX template ('plain', 'ieee', 'acm'). Defaults to 'plain'.
            timeout_sec: Maximum compilation execution timeout in seconds. Defaults to 30.

        Returns:
            Path to the compiled PDF artifact.

        Raises:
            RuntimeError: If pdflatex is missing, compilation fails, or output PDF is not generated.
        """
        export_res = await self.export_latex(project_id=project_id, template=template)
        if "error" in export_res:
            raise RuntimeError(f"LaTeX generation failed: {export_res['error']}")

        tex_path = Path(export_res["tex_path"])
        bib_path = Path(export_res["bib_path"])

        pdflatex_bin = shutil.which("pdflatex")
        if not pdflatex_bin:
            raise RuntimeError("pdflatex executable not found in system PATH")

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_tex = Path(tmpdir) / "literature_review.tex"
            tmp_bib = Path(tmpdir) / "references.bib"

            tmp_tex.write_text(tex_path.read_text(encoding="utf-8"), encoding="utf-8")
            tmp_bib.write_text(bib_path.read_text(encoding="utf-8"), encoding="utf-8")

            # Copy bundled LaTeX classes if available
            templates_dir = Path(__file__).resolve().parent.parent.parent / "templates" / "latex"
            if templates_dir.exists():
                for item in templates_dir.glob("*"):
                    if item.is_file():
                        shutil.copy(item, tmpdir)

            cmd = [pdflatex_bin, "-interaction=nonstopmode", "-file-line-error", "literature_review.tex"]

            # Pass 1: pdflatex
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=tmpdir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_sec)
            except asyncio.TimeoutError:
                proc.kill()
                raise RuntimeError(f"pdflatex compilation timed out after {timeout_sec}s")

            # Optional BibTeX and Pass 2
            bibtex_bin = shutil.which("bibtex")
            if bibtex_bin and tmp_bib.exists() and tmp_bib.stat().st_size > 0:
                try:
                    bib_proc = await asyncio.create_subprocess_exec(
                        bibtex_bin,
                        "literature_review",
                        cwd=tmpdir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await asyncio.wait_for(bib_proc.communicate(), timeout=timeout_sec)

                    p2 = await asyncio.create_subprocess_exec(
                        *cmd,
                        cwd=tmpdir,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    await asyncio.wait_for(p2.communicate(), timeout=timeout_sec)
                except Exception as exc:
                    logger.debug("BibTeX or second pass non-fatal error: %s", exc)

            tmp_pdf = Path(tmpdir) / "literature_review.pdf"
            if not tmp_pdf.exists() or tmp_pdf.stat().st_size == 0:
                stdout_str = stdout_b.decode("utf-8", errors="replace")
                stderr_str = stderr_b.decode("utf-8", errors="replace")
                errors = [
                    line for line in stdout_str.splitlines()
                    if line.startswith("!") or "Fatal error" in line
                ]
                err_msg = "\n".join(errors[:5]) if errors else (stderr_str or stdout_str[-500:])
                raise RuntimeError(f"pdflatex compilation failed (exit code {proc.returncode}): {err_msg}")

            export_dir = Path(self._projects_dir) / project_id / "exports"
            export_dir.mkdir(parents=True, exist_ok=True)

            target_pdf = export_dir / f"literature_review_{template}.pdf"
            shutil.copy(tmp_pdf, target_pdf)

            default_pdf = export_dir / "literature_review.pdf"
            shutil.copy(tmp_pdf, default_pdf)

            if self._log_service:
                await self._log_service.log_agent_trace(
                    project_id=project_id,
                    agent_name="WriterAgent",
                    event_type="tool_call",
                    details={
                        "tool": "compile_pdf",
                        "template": template,
                        "pdf_path": str(target_pdf),
                        "size_bytes": target_pdf.stat().st_size,
                    },
                )

            return target_pdf

