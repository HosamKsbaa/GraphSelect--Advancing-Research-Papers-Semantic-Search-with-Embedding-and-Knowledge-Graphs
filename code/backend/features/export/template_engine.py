"""Presentation Template Engine for ALRS v2.

Compiles modular slide definitions, inlines CSS/JS/Mermaid assets,
and produces self-contained, zero-CDN standalone HTML presentation decks.
Complies with Constitution v2.2.1 (C7 static typing, C9 <=25 line methods, FR-010 zero CDN).
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
import jinja2

from features.export.presentation_models import (
    PresentationDeckRequest,
    PresentationSlide,
    ProjectEpistemicFacts,
)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
ASSETS_DIR = TEMPLATES_DIR / "assets"


class PresentationTemplateEngine:
    """Compiles presentation slides into self-contained offline HTML documents."""

    def __init__(self, templates_dir: Path = TEMPLATES_DIR) -> None:
        self.templates_dir = templates_dir
        self.assets_dir = templates_dir / "assets"
        self.env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.templates_dir)),
            autoescape=True,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def inline_assets(self, enable_mermaid: bool = True) -> dict[str, str]:
        """Read and bundle CSS, JS, and minified Mermaid into template context."""
        css_path = self.assets_dir / "presentation_styles.css"
        js_path = self.assets_dir / "presentation_app.js"
        mermaid_path = self.assets_dir / "mermaid.min.js"

        css_content = css_path.read_text(encoding="utf-8") if css_path.exists() else ""
        js_content = js_path.read_text(encoding="utf-8") if js_path.exists() else ""
        mermaid_content = ""
        if enable_mermaid and mermaid_path.exists():
            mermaid_content = mermaid_path.read_text(encoding="utf-8")

        return {
            "inlined_css": css_content,
            "inlined_js": js_content,
            "inlined_mermaid": mermaid_content,
        }

    def render_deck(
        self,
        request: PresentationDeckRequest,
        slides: list[PresentationSlide],
        facts: ProjectEpistemicFacts,
    ) -> str:
        """Render standalone HTML presentation deck from slides and facts."""
        template = self.env.get_template("master_deck.html.j2")
        assets = self.inline_assets(enable_mermaid=request.enable_mermaid)
        context: dict[str, Any] = {
            "project_id": facts.project_id,
            "project_name": facts.project_name,
            "domain": facts.domain,
            "theme": request.theme.value,
            "enable_mermaid": request.enable_mermaid,
            "slides": slides,
            "facts": facts,
            **assets,
        }
        return template.render(context)

    @staticmethod
    def calculate_sha256(html_content: str) -> str:
        """Compute deterministic SHA-256 cryptographic fingerprint of the HTML string."""
        return hashlib.sha256(html_content.encode("utf-8")).hexdigest()
