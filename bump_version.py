#!/usr/bin/env python3
"""Bump the project version in one place.

Usage:
    python bump_version.py 2.4.0
    python bump_version.py 3.0.0-beta

This updates:
  - code/VERSION           (single source of truth)
  - code/README.md         (shields.io badge)

All other files (main.py, Dockerfile, run_graphselect.sh/.bat)
read from VERSION at runtime — no manual edits needed.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent / "code"
VERSION_FILE = ROOT / "VERSION"
README_FILE = ROOT / "README.md"


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <new_version>")
        print(f"  e.g. python {sys.argv[0]} 2.4.0")
        sys.exit(1)

    new_version = sys.argv[1].strip()

    # 1. Update VERSION file
    VERSION_FILE.write_text(new_version + "\n", encoding="utf-8")
    print(f"  [OK] VERSION     -> {new_version}")

    # 2. Update README badge (shields.io uses -- for hyphens)
    badge_version = new_version.replace("-", "--")
    readme = README_FILE.read_text(encoding="utf-8")
    readme = re.sub(
        r"(!\[Version\]\(https://img\.shields\.io/badge/version-)[^)]+(-blue\?style=flat-square\))",
        rf"\g<1>{badge_version}\2",
        readme,
    )
    README_FILE.write_text(readme, encoding="utf-8")
    print(f"  [OK] README.md   -> badge updated")

    print(f"\n  Done! Version is now: {new_version}")
    print(f"  Commit, tag (v{new_version}), and push to deploy.")


if __name__ == "__main__":
    main()
