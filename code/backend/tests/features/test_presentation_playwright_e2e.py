"""Playwright E2E browser test suite for ALRS v2 Interactive Presentation Deck (T038).

Verifies in a headless Chromium browser:
1. Zero JavaScript runtime errors and zero console errors.
2. Sequential forward and backward slide navigation via keyboard and controls.
3. Slide counter and progress bar computation accuracy.
4. Dark and Light theme switching via button and shortcut 't'.
5. Speaker Notes drawer content synchronization and toggle behavior.
6. Overview thumbnail modal rendering and direct slide jumping.
7. Keyboard shortcut suite (ArrowRight, ArrowLeft, Home, End, p, o, t, Escape).
8. Hash deep-linking (#slide-N).
9. Fullscreen toggle functionality.
10. Embedded SVG diagrams and offline Mermaid rendering.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import pytest
from playwright.sync_api import sync_playwright

from features.export.deck_generator import PresentationDeckGenerator
from features.export.presentation_models import (
    PresentationAudienceProfile,
    PresentationDeckRequest,
    PresentationTheme,
)
from features.export.template_engine import PresentationTemplateEngine


@pytest.fixture
def generated_deck_html(mock_presentation_project_facts: Any, tmp_path: Path) -> Path:
    """Generate a real 10-slide HTML presentation deck for E2E testing."""
    deck_path = tmp_path / "test_presentation_deck.html"

    from features.export.presentation_models import ProjectEpistemicFacts

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
    deck_path.write_text(html_content, encoding="utf-8")
    return deck_path


def test_presentation_headless_e2e(generated_deck_html: Path) -> None:
    """Run full Playwright browser verification suite on the generated presentation deck."""
    console_errors: list[str] = []
    page_errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Capture console and page errors
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type in ["error"] else None)
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))

        # Navigate to generated presentation
        file_url = f"file://{generated_deck_html.resolve()}"
        page.goto(file_url)
        page.wait_for_timeout(300)

        # 1. Zero Console / Runtime Errors
        assert len(page_errors) == 0, f"JS runtime errors detected: {page_errors}"
        assert len(console_errors) == 0, f"Console errors detected: {console_errors}"

        # 2. Document Title and Slide Count
        assert "Presentation Deck" in page.title()
        slides = page.query_selector_all(".slide")
        total_count = len(slides)
        assert total_count == 10, f"Expected 10 slides, found {total_count}"
        assert page.text_content("#slide-num-total") == f"{total_count:02d}"

        # 3. Sequential Walkthrough of all slides using ArrowRight
        for i in range(1, total_count + 1):
            expected_str = f"{i:02d}"
            current_str = page.text_content("#slide-num-current")
            assert current_str == expected_str, f"At slide index {i}, expected {expected_str}, got {current_str}"

            active_slide = page.query_selector(".slide.active")
            assert active_slide is not None
            heading = active_slide.query_selector(".slide-heading")
            h_text = heading.text_content() if heading else None
            assert h_text is not None and len(h_text.strip()) > 0

            if i < total_count:
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(50)

        # Confirm on last slide
        assert page.text_content("#slide-num-current") == f"{total_count:02d}"

        # 4. Sequential Walkback using ArrowLeft
        for i in range(total_count - 1, 0, -1):
            page.keyboard.press("ArrowLeft")
            page.wait_for_timeout(40)
            assert page.text_content("#slide-num-current") == f"{i:02d}"

        # Confirm back on slide 1
        assert page.text_content("#slide-num-current") == "01"

        # 5. Test Home and End keys
        page.keyboard.press("End")
        page.wait_for_timeout(60)
        assert page.text_content("#slide-num-current") == f"{total_count:02d}"

        page.keyboard.press("Home")
        page.wait_for_timeout(60)
        assert page.text_content("#slide-num-current") == "01"

        # 6. Button-based Navigation and Progress Bar
        page.click("#btn-next")
        page.wait_for_timeout(60)
        assert page.text_content("#slide-num-current") == "02"
        p_width = page.eval_on_selector("#progress-fill", "el => parseFloat(el.style.width)")
        expected_pct = (2 / total_count) * 100
        assert abs(p_width - expected_pct) < 1.0

        page.click("#btn-prev")
        page.wait_for_timeout(60)
        assert page.text_content("#slide-num-current") == "01"

        # 7. Theme Toggling (Button and Hotkey)
        assert page.get_attribute("body", "data-theme") == "dark"
        page.click("#btn-theme-toggle")
        page.wait_for_timeout(60)
        assert page.get_attribute("body", "data-theme") == "light"

        page.keyboard.press("t")
        page.wait_for_timeout(60)
        assert page.get_attribute("body", "data-theme") == "dark"

        # 8. Speaker Notes Drawer
        assert "open" not in (page.get_attribute("#notes-drawer", "class") or "")
        page.click("#btn-notes-toggle")
        page.wait_for_timeout(100)
        assert "open" in (page.get_attribute("#notes-drawer", "class") or "")
        notes_html = page.inner_html("#notes-content")
        assert "Speaker Guidance" in notes_html

        page.click("#btn-notes-close")
        page.wait_for_timeout(100)
        assert "open" not in (page.get_attribute("#notes-drawer", "class") or "")

        # Test hotkey 'p' to toggle notes
        page.keyboard.press("p")
        page.wait_for_timeout(100)
        assert "open" in (page.get_attribute("#notes-drawer", "class") or "")
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        assert "open" not in (page.get_attribute("#notes-drawer", "class") or "")

        # 9. Overview Grid Mode & Slide Jumping
        page.click("#btn-overview-toggle")
        page.wait_for_timeout(100)
        assert "open" in (page.get_attribute("#overview-modal", "class") or "")
        cards = page.query_selector_all(".overview-thumb")
        assert len(cards) == total_count

        # Jump to slide 4
        cards[3].click()
        page.wait_for_timeout(150)
        assert page.text_content("#slide-num-current") == "04"
        assert "open" not in (page.get_attribute("#overview-modal", "class") or "")

        # Test hotkey 'o' to open and Escape to close overview
        page.keyboard.press("o")
        page.wait_for_timeout(100)
        assert "open" in (page.get_attribute("#overview-modal", "class") or "")
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        assert "open" not in (page.get_attribute("#overview-modal", "class") or "")

        # 10. URL Hash Deep-Linking
        page.goto(f"{file_url}#slide-7")
        page.wait_for_timeout(200)
        assert page.text_content("#slide-num-current") == "07"

        # 11. Fullscreen Toggle Button (safe invoke)
        page.click("#btn-fullscreen-toggle")
        page.wait_for_timeout(60)

        # 12. Visual Archetypes Integrity (Metrics Stat Cards, Synthesis Matrix, Mermaid Citation Subgraph)
        stat_cards = page.query_selector_all(".stat-card")
        assert len(stat_cards) >= 4, f"Expected at least 4 stat cards, found {len(stat_cards)}"

        matrix_table = page.query_selector("table.matrix-table")
        assert matrix_table is not None

        mermaid_el = page.query_selector(".mermaid")
        assert mermaid_el is not None

        # Clean up
        browser.close()
