#!/usr/bin/env python3
"""
Deterministic CI gate: fail if placeholder/stub markers or NotImplementedError/501
remain in non-test code, docs, policy, or config.

Scans repo recursively with exclusions; prints file:line:token on failure; exit 1 if any.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# Directories to skip when scanning
EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "venv",
    "dist",
    "site",
    "__pycache__",
    "node_modules",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    "build",
}


def _is_excluded_path(rel_path: str) -> bool:
    parts = rel_path.split("/")
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
        if part.endswith(".egg-info"):
            return True
    return False


# Text extensions to scan (skip others to avoid binary)
TEXT_EXTENSIONS = {
    ".py",
    ".md",
    ".yml",
    ".yaml",
    ".json",
    ".jsonl",
    ".txt",
    ".sh",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".rst",
    ".cfg",
    ".ini",
    ".toml",
}

# --- Global fail: these substrings must not appear in any file ---
GLOBAL_FAIL_PATTERNS = [
    "NotImplementedError",
    "501 Not Implemented",
    "ACTION_QUEUE_RUN_PLACEHOLDER",
    "OBS_PLACEHOLDER",
    '"algorithm": "stub"',
    "'algorithm': 'stub'",
    "algorithm: stub",
    '"status": "stub"',
    "'status': 'stub'",
    "status: stub",
    "status=stub",
]

# Paths that are checked for words "placeholder" / "stub" (prefix match, normalized).
# docs/, policy/, src/, tests/, mkdocs.yml: no placeholder; no lowercase stub (tests/ may use capital-S Stub).
WORD_CHECK_PREFIXES = ("docs/", "policy/", "src/", "tests/", "mkdocs.yml")

# In tests/, allow capital-S "Stub" (e.g. StubTask); still fail on lowercase "stub" and "placeholder"
# secret_scrubber.py may contain "placeholder" (parameter name)
SECRET_SCRUBBER_NAME = "secret_scrubber.py"

# Files that define or test the gate itself: skip to avoid self-fail
EXCLUDE_FILES = {"tools/no_placeholders.py", "tests/test_no_placeholders.py"}


def _norm_path(path: Path, root: Path) -> str:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return path.as_posix()
    return rel.as_posix()


def _should_scan_file(path: Path, root: Path) -> bool:
    rel = _norm_path(path, root)
    if _is_excluded_path(rel):
        return False
    if rel in EXCLUDE_FILES:
        return False
    if path.suffix.lower() not in TEXT_EXTENSIONS and path.name != "mkdocs.yml":
        return False
    return True


def _read_lines(path: Path) -> list[str] | None:
    try:
        raw = path.read_bytes()
    except OSError:
        return None
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return text.splitlines()


def _is_under_tests_for_skip(rel_path: str) -> bool:
    """True if path is under tests/ (skip GLOBAL_FAIL there so tests can assert on these patterns)."""
    return rel_path.startswith("tests/")


def _check_global_fails(path: Path, root: Path, lines: list[str]) -> list[tuple[int, str]]:
    violations: list[tuple[int, str]] = []
    rel_path = _norm_path(path, root)
    if _is_under_tests_for_skip(rel_path):
        return []
    for i, line in enumerate(lines, start=1):
        for pat in GLOBAL_FAIL_PATTERNS:
            if pat in line:
                violations.append((i, pat))
    return violations


def _is_secret_scrubber(rel_path: str) -> bool:
    return rel_path.endswith(SECRET_SCRUBBER_NAME) or SECRET_SCRUBBER_NAME in rel_path


def _word_check_applies(rel_path: str) -> bool:
    for prefix in WORD_CHECK_PREFIXES:
        if prefix == "mkdocs.yml":
            if rel_path == "mkdocs.yml":
                return True
        elif rel_path.startswith(prefix):
            return True
    return False


def _check_word_placeholder_stub(path: Path, root: Path, lines: list[str]) -> list[tuple[int, str]]:
    rel_path = _norm_path(path, root)
    if not _word_check_applies(rel_path):
        return []

    under_tests = rel_path.startswith("tests/")
    violations: list[tuple[int, str]] = []
    for i, line in enumerate(lines, start=1):
        # Allow secret_scrubber.py to use "placeholder" (parameter)
        if _is_secret_scrubber(rel_path) and "placeholder" in line.lower():
            continue
        if "placeholder" in line.lower():
            violations.append((i, "placeholder"))
        # In tests/, allow capital-S "Stub" (e.g. StubTask); fail only on lowercase "stub"
        if "stub" in line.lower():
            if under_tests and re.search(r"\bstub\b", line):
                violations.append((i, "stub"))
            elif not under_tests:
                violations.append((i, "stub"))
    return violations


def _iter_scannable_files(root: Path) -> list[Path]:
    """Yield all scannable file paths under root (excluding EXCLUDE_DIRS and non-text)."""
    root = root.resolve()
    out: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if not _should_scan_file(path, root):
            continue
        out.append(path)
    return out


def scan_root(root: Path) -> list[tuple[Path, int, str]]:
    root = root.resolve()
    results: list[tuple[Path, int, str]] = []

    for path in _iter_scannable_files(root):
        lines = _read_lines(path)
        if lines is None:
            continue

        for line_no, token in _check_global_fails(path, root, lines):
            results.append((path, line_no, token))
        for line_no, token in _check_word_placeholder_stub(path, root, lines):
            results.append((path, line_no, token))

    return results


def main() -> int:
    root = Path.cwd()
    if len(sys.argv) > 1:
        root = Path(sys.argv[1]).resolve()

    violations = scan_root(root)
    for path, line_no, token in sorted(violations, key=lambda x: (str(x[0]), x[1])):
        rel = _norm_path(path, root)
        print(f"{rel}:{line_no}: {token!r}")

    return 1 if violations else 0


if __name__ == "__main__":
    sys.exit(main())
