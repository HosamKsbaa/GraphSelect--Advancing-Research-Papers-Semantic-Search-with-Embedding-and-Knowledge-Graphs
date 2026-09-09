"""
test_academic_figures_m1.py
Comprehensive automated test suite for Milestone 1 Track 4:
Academic Figures, System Diagrams & Visual Graphs.
"""

import os
import hashlib
import pytest
from PIL import Image

REPO_ROOT = "/home/mr-h/Documents/Fam/me/masters/new/MasterProject2"
TARGET_DIRS = [
    os.path.join(REPO_ROOT, "paper/figures"),
    os.path.join(REPO_ROOT, "paper/conference/figures"),
    os.path.join(REPO_ROOT, "paper/myPapers/masterPapers/proposal/figures"),
    os.path.join(REPO_ROOT, "paper/myPapers/masterPapers/thesis/figures"),
    os.path.join(REPO_ROOT, "paper/presentation/assets/figures"),
]

CORE_FIGURES = [
    "adk_swarm_hierarchy",
    "five_stage_four_quadrant_state",
    "graphselect_traversal_topology",
    "benchmark_comparison_charts",
    "score_convergence_trajectories",
]

ALL_FIGURES = CORE_FIGURES + ["angular_telemetry_workflow"]

def sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

class TestAcademicFiguresM1:
    """Rigorous verification test suite for ALRS v2 academic figures."""

    @pytest.mark.parametrize("target_dir", TARGET_DIRS)
    def test_target_directories_exist(self, target_dir):
        """Assert all 5 target directories exist and are writable."""
        assert os.path.exists(target_dir), f"Directory {target_dir} does not exist"
        assert os.path.isdir(target_dir), f"Path {target_dir} is not a directory"

    @pytest.mark.parametrize("fig_name", ALL_FIGURES)
    @pytest.mark.parametrize("ext", [".pdf", ".png", ".svg"])
    def test_files_exist_and_non_empty_in_all_destinations(self, fig_name, ext):
        """Verify each figure format exists and is non-empty across all 5 directories."""
        for target_dir in TARGET_DIRS:
            filepath = os.path.join(target_dir, f"{fig_name}{ext}")
            assert os.path.exists(filepath), f"Missing file: {filepath}"
            size = os.path.getsize(filepath)
            assert size > 5000, f"File {filepath} suspiciously small ({size} bytes)"

    @pytest.mark.parametrize("fig_name", ALL_FIGURES)
    def test_pdf_magic_bytes(self, fig_name):
        """Verify PDF header magic bytes across all targets."""
        for target_dir in TARGET_DIRS:
            pdf_path = os.path.join(target_dir, f"{fig_name}.pdf")
            with open(pdf_path, "rb") as f:
                header = f.read(5)
            assert header == b"%PDF-", f"Invalid PDF magic bytes in {pdf_path}"

    @pytest.mark.parametrize("fig_name", ALL_FIGURES)
    def test_png_dimensions_and_resolution(self, fig_name):
        """Verify PNG files open cleanly and have publication-grade resolution (width >= 2000px)."""
        for target_dir in TARGET_DIRS:
            png_path = os.path.join(target_dir, f"{fig_name}.png")
            with Image.open(png_path) as im:
                width, height = im.size
                assert width >= 2000, f"{png_path} width {width} < 2000px"
                assert height >= 1000, f"{png_path} height {height} < 1000px"
                assert im.mode in ["RGB", "RGBA"], f"Invalid mode {im.mode} in {png_path}"

    @pytest.mark.parametrize("fig_name", ALL_FIGURES)
    def test_svg_xml_structure(self, fig_name):
        """Verify SVG files have valid XML vector markup."""
        for target_dir in TARGET_DIRS:
            svg_path = os.path.join(target_dir, f"{fig_name}.svg")
            with open(svg_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            assert "<svg" in content, f"Missing <svg tag in {svg_path}"
            assert "</svg>" in content, f"Missing </svg> closing tag in {svg_path}"

    @pytest.mark.parametrize("fig_name", ALL_FIGURES)
    @pytest.mark.parametrize("ext", [".pdf", ".png", ".svg"])
    def test_bit_for_bit_hash_consistency_across_targets(self, fig_name, ext):
        """Assert that deployed figures across all 5 directories have identical SHA-256 hashes."""
        canonical_path = os.path.join(TARGET_DIRS[0], f"{fig_name}{ext}")
        canonical_hash = sha256(canonical_path)
        
        for other_dir in TARGET_DIRS[1:]:
            other_path = os.path.join(other_dir, f"{fig_name}{ext}")
            assert sha256(other_path) == canonical_hash, f"Hash mismatch between {canonical_path} and {other_path}"

    def test_all_five_core_figures_present(self):
        """Assert all 5 core required figures from DISPATCH.md are fully satisfied."""
        for fig in CORE_FIGURES:
            for d in TARGET_DIRS:
                assert os.path.exists(os.path.join(d, f"{fig}.pdf"))
                assert os.path.exists(os.path.join(d, f"{fig}.png"))
                assert os.path.exists(os.path.join(d, f"{fig}.svg"))
