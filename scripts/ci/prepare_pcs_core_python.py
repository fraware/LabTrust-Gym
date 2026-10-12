"""Prepare a pinned upstream PCS Python checkout for editable CI installation.

The PCS project's PEP 621 readme currently refers outside its Python
project root. Copy the tracked upstream README inside that root and fix only
the metadata reference, with exact source/revision checks and no silent
fallback to a different dependency tree.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

PINNED_PCS_CORE_COMMIT = "9c971f5f9da8a424924dd8f48d6a3b71a1009e1b"
BROKEN_README_DECLARATION = 'readme = "../README.md"'


def prepare(checkout: Path) -> None:
    checkout = checkout.resolve(strict=True)
    actual_revision = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual_revision != PINNED_PCS_CORE_COMMIT:
        raise RuntimeError(f"PCS version mismatch: {actual_revision}")
    project = checkout / "python"
    pyproject = project / "pyproject.toml"
    source_readme = checkout / "README.md"
    installed_readme = project / "README.md"
    if not pyproject.is_file() or not source_readme.is_file():
        raise RuntimeError("Expected pinned PCS packaging inputs are absent")
    content = pyproject.read_text(encoding="utf-8")
    if content.count(BROKEN_README_DECLARATION) != 1 or installed_readme.exists():
        raise RuntimeError("Unexpected PCS metadata state; review upstream change")
    shutil.copyfile(source_readme, installed_readme)
    pyproject.write_text(
        content.replace(BROKEN_README_DECLARATION, 'readme = "README.md"'),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    args = parser.parse_args()
    prepare(args.checkout)


if __name__ == "__main__":
    main()
