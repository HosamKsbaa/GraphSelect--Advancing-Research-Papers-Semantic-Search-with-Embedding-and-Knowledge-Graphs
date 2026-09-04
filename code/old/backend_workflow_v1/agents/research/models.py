"""Pydantic data models for Literature Analysis and Evidence Synthesis (Milestone 2 / R2)."""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


class PaperFinding(BaseModel):
    """Structured extraction of methodology, empirical results, benchmarks, and limitations for a single paper."""

    doi: str = Field(description="Digital Object Identifier of the paper")
    title: str = Field(description="Title of the paper")
    year: int | None = Field(default=None, description="Year of publication")
    methodology: str = Field(description="Summary of approach, models, architectures, or algorithms used")
    key_findings: list[str] = Field(
        default_factory=list,
        description="Key empirical results, quantitative findings, and theoretical takeaways",
    )
    datasets_or_benchmarks: list[str] = Field(
        default_factory=list,
        description="Datasets, benchmarks, or environments evaluated on",
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="Stated or observed limitations, threats to validity, or edge cases",
    )


class ComparisonDimension(BaseModel):
    """A comparative dimension (theme, metric, scale, technique) across multiple papers."""

    dimension_name: str = Field(
        description="Feature or theme being compared (e.g. Scalability, Accuracy, Graph Sparsity, Expressive Power)"
    )
    findings_by_doi: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of paper DOI to its specific stance, performance, or finding along this dimension",
    )
    consensus: str = Field(
        default="",
        description="Agreed-upon findings or common patterns across papers",
    )
    divergence: str = Field(
        default="",
        description="Contradictions, trade-offs, varying assumptions, or differing conclusions across papers",
    )


class StructuredComparisonMatrix(BaseModel):
    """Comprehensive multi-paper literature comparison matrix with narrative synthesis."""

    project_id: str = Field(description="Project identifier")
    research_questions: list[str] = Field(
        default_factory=list,
        description="Research questions addressing this literature synthesis",
    )
    dimensions: list[ComparisonDimension] = Field(
        default_factory=list,
        description="List of comparison dimensions evaluated across papers",
    )
    synthesis_narrative: str = Field(
        default="",
        description="High-level narrative synthesizing cross-paper insights, consensus, and open challenges",
    )

    def to_markdown_table(self) -> str:
        """Render the structured matrix as a GitHub-flavored Markdown table."""
        if not self.dimensions:
            return "No comparison dimensions defined."

        all_dois: list[str] = []
        for dim in self.dimensions:
            for doi in dim.findings_by_doi.keys():
                if doi not in all_dois:
                    all_dois.append(doi)

        if not all_dois:
            headers = ["Dimension", "Consensus", "Divergence"]
            rows: list[list[str]] = []
            for dim in self.dimensions:
                rows.append([
                    dim.dimension_name,
                    dim.consensus.replace("|", "\\|") or "—",
                    dim.divergence.replace("|", "\\|") or "—",
                ])
        else:
            headers = ["Dimension"] + all_dois + ["Consensus", "Divergence"]
            rows = []
            for dim in self.dimensions:
                row = [dim.dimension_name]
                for doi in all_dois:
                    val = dim.findings_by_doi.get(doi, "N/A").replace("|", "\\|")
                    row.append(val)
                row.append(dim.consensus.replace("|", "\\|") or "—")
                row.append(dim.divergence.replace("|", "\\|") or "—")
                rows.append(row)

        header_line = "| " + " | ".join(headers) + " |"
        sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
        row_lines = ["| " + " | ".join(r) + " |" for r in rows]
        return "\n".join([header_line, sep_line] + row_lines)

    def to_dict(self) -> dict[str, Any]:
        """Serialize matrix to a JSON-compatible dictionary."""
        return self.model_dump()
