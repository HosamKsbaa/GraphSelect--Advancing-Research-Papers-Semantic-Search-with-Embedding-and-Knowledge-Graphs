"""AST-based architectural boundary checks for `code/backend/engines/`.

Enforces:
1. Modules inside `engines/` never import `api` or `ai`.
2. Modules outside `engines/` import only `engines.<pkg>` (or top-level `engines.papers`
   / `engines.errors`), never internal submodules like `engines.openalex.budget`.
"""

from __future__ import annotations

import ast
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
ENGINES_DIR = BACKEND_ROOT / "engines"
TOP_LEVEL_ENGINE_MODULES = {"papers", "errors", "budget"}


def iter_python_files(directory: Path) -> list[Path]:
    return sorted(p for p in directory.rglob("*.py") if ".venv" not in p.parts)


def imported_targets(py_file: Path) -> list[tuple[int, str]]:
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.append((node.lineno, alias.name))
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.append((node.lineno, node.module))
    return found


def test_engines_never_import_api_or_ai() -> None:
    violations: list[str] = []
    for py_file in iter_python_files(ENGINES_DIR):
        rel = py_file.relative_to(BACKEND_ROOT)
        for lineno, target in imported_targets(py_file):
            root_pkg = target.split(".")[0]
            if root_pkg in {"api", "ai", "routers", "services", "models"}:
                violations.append(f"{rel}:{lineno} imports forbidden module '{target}'")
    assert not violations, "Engine boundary violations:\n" + "\n".join(violations)


def test_external_callers_only_import_engine_public_interfaces() -> None:
    violations: list[str] = []
    for py_file in iter_python_files(BACKEND_ROOT):
        if py_file.is_relative_to(ENGINES_DIR):
            continue
        rel = py_file.relative_to(BACKEND_ROOT)
        for lineno, target in imported_targets(py_file):
            parts = target.split(".")
            if parts[0] != "engines":
                continue
            # Allowed: `engines`, `engines.<pkg>`, or `engines.<top_level_module>`
            if len(parts) > 2:
                violations.append(
                    f"{rel}:{lineno} imports internal engine module '{target}' "
                    f"(import from 'engines.{parts[1]}' instead)"
                )
    assert not violations, "Public engine interface violations:\n" + "\n".join(violations)
