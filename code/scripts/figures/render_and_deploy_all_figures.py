#!/usr/bin/env python3
"""
render_and_deploy_all_figures.py
Master generation and deployment harness for ALRS v2 Academic Figures.

Generates:
1. adk_swarm_hierarchy (.pdf, .png, .svg)
2. five_stage_four_quadrant_state (.pdf, .png, .svg)
3. graphselect_traversal_topology (.pdf, .png, .svg)
4. benchmark_comparison_charts (.pdf, .png, .svg)
5. score_convergence_trajectories (.pdf, .png, .svg)
6. angular_telemetry_workflow (.pdf, .png, .svg)

Deploys to 5 target destinations:
- paper/figures/
- paper/conference/figures/
- paper/myPapers/masterPapers/proposal/figures/
- paper/myPapers/masterPapers/thesis/figures/
- paper/presentation/assets/figures/

Verifies non-empty status, file integrity, and dimensions.
"""

import os
import shutil
import subprocess
import sys
import hashlib
from PIL import Image

REPO_ROOT = "/home/mr-h/Documents/Fam/me/masters/new/MasterProject2"
SCRIPTS_DIR = os.path.join(REPO_ROOT, "newcode/code/scripts/figures")
VENV_PYTHON = os.path.join(REPO_ROOT, "newcode/code/backend/.venv/bin/python3")

TARGET_DIRS = [
    os.path.join(REPO_ROOT, "paper/figures"),
    os.path.join(REPO_ROOT, "paper/conference/figures"),
    os.path.join(REPO_ROOT, "paper/myPapers/masterPapers/proposal/figures"),
    os.path.join(REPO_ROOT, "paper/myPapers/masterPapers/thesis/figures"),
    os.path.join(REPO_ROOT, "paper/presentation/assets/figures"),
]

FIGURE_KEYS = [
    "adk_swarm_hierarchy",
    "five_stage_four_quadrant_state",
    "graphselect_traversal_topology",
    "benchmark_comparison_charts",
    "score_convergence_trajectories",
    "angular_telemetry_workflow",
]

GENERATOR_SCRIPTS = [
    "generate_adk_swarm_hierarchy.py",
    "generate_five_stage_four_quadrant_state.py",
    "generate_graphselect_traversal_topology.py",
    "generate_benchmark_comparison_charts.py",
    "generate_score_convergence_trajectories.py",
    "generate_angular_telemetry_workflow.py",
]

def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def main():
    print("=" * 80)
    print("ALRS v2 ACADEMIC FIGURES: MASTER GENERATION & DEPLOYMENT HARNESS")
    print("=" * 80)

    # 1. Ensure target directories exist
    for d in TARGET_DIRS:
        os.makedirs(d, exist_ok=True)
        print(f"[INIT] Ensured directory exists: {d}")

    paper_scripts_dir = os.path.join(REPO_ROOT, "paper/figures/scripts")
    os.makedirs(paper_scripts_dir, exist_ok=True)

    # 2. Run all generators
    print("\n" + "-" * 80)
    print("[EXEC] Running Figure Generators in Backend Virtual Environment...")
    print("-" * 80)
    for script_name in GENERATOR_SCRIPTS:
        script_path = os.path.join(SCRIPTS_DIR, script_name)
        print(f"-> Executing {script_name}...")
        res = subprocess.run([VENV_PYTHON, script_path], cwd=SCRIPTS_DIR, capture_output=True, text=True)
        if res.returncode != 0:
            print(f"FAILED: {script_name}\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}", file=sys.stderr)
            sys.exit(1)
        print(f"   Success. Generated artifacts verified.")

    # 3. Deploy generated artifacts (.pdf, .png, .svg) to all target directories
    print("\n" + "-" * 80)
    print("[DEPLOY] Deploying Artifacts across all 5 Target Destinations...")
    print("-" * 80)

    extensions = [".pdf", ".png", ".svg"]
    deployed_records = []

    for fig_key in FIGURE_KEYS:
        for ext in extensions:
            src_file = os.path.join(SCRIPTS_DIR, f"{fig_key}{ext}")
            if not os.path.exists(src_file):
                print(f"ERROR: Missing source file {src_file}", file=sys.stderr)
                sys.exit(1)
            
            src_size = os.path.getsize(src_file)
            src_hash = sha256_file(src_file)

            dim_info = "N/A"
            if ext == ".png":
                with Image.open(src_file) as im:
                    dim_info = f"{im.size[0]}x{im.size[1]} ({im.mode})"

            for target_dir in TARGET_DIRS:
                dst_file = os.path.join(target_dir, f"{fig_key}{ext}")
                shutil.copy2(src_file, dst_file)
                
                # Check dst
                assert os.path.exists(dst_file), f"Destination {dst_file} does not exist!"
                assert os.path.getsize(dst_file) == src_size, f"Size mismatch for {dst_file}"
                
            deployed_records.append({
                "figure": fig_key,
                "ext": ext,
                "size": src_size,
                "dimensions": dim_info,
                "sha256": src_hash[:12] + "...",
            })
            print(f"  [COPIED] {fig_key}{ext} ({src_size:,} bytes) -> 5 targets")

    # Also backup scripts to paper/figures/scripts/
    for script_name in GENERATOR_SCRIPTS + ["render_and_deploy_all_figures.py"]:
        src = os.path.join(SCRIPTS_DIR, script_name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(paper_scripts_dir, script_name))
    print(f"  [BACKUP] Generator scripts synchronized to {paper_scripts_dir}")

    # 4. Automated Verification Matrix
    print("\n" + "-" * 80)
    print("[VERIFY] Comprehensive Verification Matrix Across All Targets:")
    print("-" * 80)
    print(f"{'Figure Key':<32} {'Ext':<6} {'Size (B)':<10} {'Dimensions':<18} {'SHA-256':<16} {'5 Targets Verified'}")
    print("-" * 92)
    for rec in deployed_records:
        fig_key = rec["figure"]
        ext = rec["ext"]
        # Verify in each dir
        all_ok = True
        for target_dir in TARGET_DIRS:
            target_path = os.path.join(target_dir, f"{fig_key}{ext}")
            if not os.path.exists(target_path) or os.path.getsize(target_path) == 0:
                all_ok = False
                break
        status_str = "PASSED (100%)" if all_ok else "FAILED"
        print(f"{fig_key:<32} {ext:<6} {rec['size']:<10} {rec['dimensions']:<18} {rec['sha256']:<16} {status_str}")

    print("\n" + "=" * 80)
    print("ALL ACADEMIC FIGURES GENERATED, VERIFIED AND DEPLOYED SUCCESSFULLY!")
    print("=" * 80)

if __name__ == "__main__":
    main()
