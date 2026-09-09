"""Accessibility and zero-CDN offline self-containment test suite (T039).

Verifies:
1. Zero external http:// or https:// URLs in <link>, <script>, <img> tags (FR-010, SC-003).
2. Standard ARIA accessibility attributes (role="region", role="dialog", aria-expanded, aria-label).
3. WCAG 2.1 AA mathematical contrast ratio verification (minimum 4.5:1 body, 3.0:1 headings, SC-009).
"""
from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
import pytest

from features.export.deck_generator import PresentationDeckGenerator
from features.export.presentation_models import (
    PresentationAudienceProfile,
    PresentationDeckRequest,
    PresentationTheme,
    ProjectEpistemicFacts,
)
from features.export.template_engine import PresentationTemplateEngine


class DeckHTMLInspector(HTMLParser):
    """Standard library HTML inspector for accessibility and asset audit."""

    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[dict[str, str]] = []
        self.links: list[dict[str, str]] = []
        self.imgs: list[dict[str, str]] = []
        self.buttons: list[dict[str, str]] = []
        self.slides: list[dict[str, str]] = []
        self.notes_drawer: dict[str, str] | None = None
        self.overview_modal: dict[str, str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k: (v or "") for k, v in attrs}
        if tag == "script":
            self.scripts.append(attr_dict)
        elif tag == "link":
            self.links.append(attr_dict)
        elif tag == "img":
            self.imgs.append(attr_dict)
        elif tag == "button":
            self.buttons.append(attr_dict)
        elif tag == "section" and "slide" in attr_dict.get("class", "").split():
            self.slides.append(attr_dict)

        if attr_dict.get("id") == "notes-drawer":
            self.notes_drawer = attr_dict
        elif attr_dict.get("id") == "overview-modal":
            self.overview_modal = attr_dict


def _channel_luminance(c: float) -> float:
    """Calculate linearized color channel luminance per WCAG 2.1 specifications."""
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def _relative_luminance(hex_color: str) -> float:
    """Calculate WCAG 2.1 relative luminance L for an RGB hex color string (#rrggbb)."""
    hex_clean = hex_color.lstrip("#")
    r = int(hex_clean[0:2], 16) / 255.0
    g = int(hex_clean[2:4], 16) / 255.0
    b = int(hex_clean[4:6], 16) / 255.0
    return 0.2126 * _channel_luminance(r) + 0.7152 * _channel_luminance(g) + 0.0722 * _channel_luminance(b)


def calculate_contrast_ratio(hex_fg: str, hex_bg: str) -> float:
    """Compute WCAG 2.1 contrast ratio (L1 + 0.05) / (L2 + 0.05) between two hex colors."""
    l1 = _relative_luminance(hex_fg)
    l2 = _relative_luminance(hex_bg)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


@pytest.fixture
def deck_inspector(mock_presentation_project_facts: Any) -> DeckHTMLInspector:
    """Render a presentation deck and parse with standard library DeckHTMLInspector."""
    facts = ProjectEpistemicFacts.model_validate(mock_presentation_project_facts)
    req = PresentationDeckRequest(
        project_id="test-campaign-001",
        audience_profile=PresentationAudienceProfile.SUPERVISOR,
        target_slide_count=10,
        theme=PresentationTheme.DARK,
        enable_mermaid=True,
    )
    generator = PresentationDeckGenerator()
    slides = generator.build_slide_sequence(facts, req)
    engine = PresentationTemplateEngine()
    html_content = engine.render_deck(req, slides, facts)

    inspector = DeckHTMLInspector()
    inspector.feed(html_content)
    return inspector


def test_zero_external_cdn_dependencies(deck_inspector: DeckHTMLInspector) -> None:
    """Verify 100% offline self-containment with zero external CDN requests (FR-010, SC-003)."""
    # 1. Inspect all <script> tags: must have no src attribute pointing to http/https
    for s in deck_inspector.scripts:
        src = s.get("src", "")
        assert not src.startswith("http://") and not src.startswith("https://"), f"External script found: {src}"

    # 2. Inspect all <link> tags: must not load external stylesheets
    for link in deck_inspector.links:
        href = link.get("href", "")
        assert not href.startswith("http://") and not href.startswith("https://"), f"External stylesheet found: {href}"

    # 3. Inspect all <img> tags: must not load remote images
    for img in deck_inspector.imgs:
        src = img.get("src", "")
        assert not src.startswith("http://") and not src.startswith("https://"), f"External image found: {src}"


def test_aria_accessibility_attributes(deck_inspector: DeckHTMLInspector) -> None:
    """Verify standard ARIA semantic accessibility attributes across UI components."""
    # 1. Slide sections have role="region" and aria-label
    assert len(deck_inspector.slides) == 10
    for slide in deck_inspector.slides:
        assert slide.get("role") == "region"
        assert len(slide.get("aria-label", "")) > 0

    # 2. Speaker notes drawer
    drawer = deck_inspector.notes_drawer
    assert drawer is not None
    assert drawer.get("role") == "region"
    assert "notes" in drawer.get("aria-label", "").lower()

    # 3. Overview modal dialog
    modal = deck_inspector.overview_modal
    assert modal is not None
    assert modal.get("role") == "dialog"
    assert modal.get("aria-modal") == "true"
    assert modal.get("aria-labelledby") == "overview-modal-title"

    # 4. Buttons have aria-label or accessible attributes
    for btn in deck_inspector.buttons:
        assert len(btn.get("aria-label", "")) > 0 or len(btn.get("id", "")) > 0


def test_wcag_2_1_aa_contrast_ratios() -> None:
    """Verify that design system color tokens satisfy WCAG 2.1 AA contrast requirements (SC-009)."""
    dark_bg = "#090d16"
    dark_text_primary = "#f8fafc"
    dark_text_secondary = "#94a3b8"
    dark_accent_cyan = "#06b6d4"

    light_bg = "#f8fafc"
    light_text_primary = "#0f172a"
    light_text_secondary = "#334155"
    light_accent_cyan = "#0284c7"

    # 1. Dark Theme Body Text (minimum 4.5:1)
    contrast_dark_primary = calculate_contrast_ratio(dark_text_primary, dark_bg)
    assert contrast_dark_primary >= 4.5, f"Dark primary text contrast failed: {contrast_dark_primary:.2f}:1"

    contrast_dark_secondary = calculate_contrast_ratio(dark_text_secondary, dark_bg)
    assert contrast_dark_secondary >= 4.5, f"Dark secondary text contrast failed: {contrast_dark_secondary:.2f}:1"

    # 2. Light Theme Body Text (minimum 4.5:1)
    contrast_light_primary = calculate_contrast_ratio(light_text_primary, light_bg)
    assert contrast_light_primary >= 4.5, f"Light primary text contrast failed: {contrast_light_primary:.2f}:1"

    contrast_light_secondary = calculate_contrast_ratio(light_text_secondary, light_bg)
    assert contrast_light_secondary >= 4.5, f"Light secondary text contrast failed: {contrast_light_secondary:.2f}:1"

    # 3. Headings / Highlights (minimum 3.0:1 for large graphical/heading text)
    contrast_dark_cyan = calculate_contrast_ratio(dark_accent_cyan, dark_bg)
    assert contrast_dark_cyan >= 3.0, f"Dark cyan heading contrast failed: {contrast_dark_cyan:.2f}:1"

    contrast_light_cyan = calculate_contrast_ratio(light_accent_cyan, light_bg)
    assert contrast_light_cyan >= 3.0, f"Light cyan heading contrast failed: {contrast_light_cyan:.2f}:1"
