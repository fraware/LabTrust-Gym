"""
Unit tests for tools/no_placeholders.py scanner.

Creates temp repo structures and asserts allow/deny logic by path.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.no_placeholders import _norm_path, scan_root


def _write_tree(tmp_path: Path, files: dict[str, str]) -> None:
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def test_global_fail_not_implemented_error(tmp_path: Path) -> None:
    _write_tree(tmp_path, {"src/foo.py": "raise NotImplementedError\n"})
    violations = scan_root(tmp_path)
    rels = [_norm_path(p, tmp_path) for p, _, t in violations if t == "NotImplementedError"]
    assert "src/foo.py" in rels


def test_global_fail_501_not_implemented(tmp_path: Path) -> None:
    _write_tree(tmp_path, {"docs/readme.md": "Returns 501 Not Implemented.\n"})
    violations = scan_root(tmp_path)
    rels = [_norm_path(p, tmp_path) for p, _, t in violations if "501" in t]
    assert any("readme.md" in r for r in rels)


def test_global_fail_status_stub(tmp_path: Path) -> None:
    _write_tree(tmp_path, {"src/bar.json": '{"status": "stub"}\n'})
    violations = scan_root(tmp_path)
    tokens = [t for _, _, t in violations]
    assert '"status": "stub"' in tokens or "status" in str(tokens)


def test_word_check_docs_placeholder(tmp_path: Path) -> None:
    """docs/ is in ALLOWED_PLACEHOLDER_PATH_PREFIXES; placeholder there is allowed."""
    _write_tree(tmp_path, {"docs/foo.md": "This is a placeholder.\n"})
    violations = scan_root(tmp_path)
    rels = [_norm_path(p, tmp_path) for p, _, t in violations if t == "placeholder"]
    assert not any("docs" in r and "foo.md" in r for r in rels)


def test_word_check_docs_stub(tmp_path: Path) -> None:
    """docs/ is in ALLOWED_STUB_PATH_PREFIXES; stub there is allowed."""
    _write_tree(tmp_path, {"docs/bar.md": "Stub implementation.\n"})
    violations = scan_root(tmp_path)
    rels = [_norm_path(p, tmp_path) for p, _, t in violations if t == "stub"]
    assert not any("docs" in r and "bar.md" in r for r in rels)


def test_tests_allow_capital_stub(tmp_path: Path) -> None:
    _write_tree(tmp_path, {"tests/test_foo.py": "class StubTask:\n    pass\n"})
    violations = scan_root(tmp_path)
    stub_violations = [
        (p, ln, t) for p, ln, t in violations if _norm_path(p, tmp_path).startswith("tests/") and t == "stub"
    ]
    assert not stub_violations


def test_tests_fail_placeholder(tmp_path: Path) -> None:
    """tests/ is in ALLOWED_PLACEHOLDER_PATH_PREFIXES; placeholder there is allowed."""
    _write_tree(tmp_path, {"tests/test_baz.py": "x = 'placeholder'\n"})
    violations = scan_root(tmp_path)
    rels = [_norm_path(p, tmp_path) for p, _, t in violations if t == "placeholder"]
    assert not any("tests" in r for r in rels)


def test_tests_fail_lowercase_stub(tmp_path: Path) -> None:
    """tests/ is in ALLOWED_STUB_PATH_PREFIXES; lowercase stub there is allowed."""
    _write_tree(tmp_path, {"tests/test_qux.py": "status = 'stub'\n"})
    violations = scan_root(tmp_path)
    assert not any(_norm_path(p, tmp_path).startswith("tests/") for p, _, _ in violations)


def test_secret_scrubber_allows_placeholder(tmp_path: Path) -> None:
    _write_tree(
        tmp_path,
        {
            "src/labtrust_gym/security/secret_scrubber.py": ("def scrub(text, placeholder='<redacted>'):\n    pass\n"),
        },
    )
    violations = scan_root(tmp_path)
    scrubber_violations = [
        v for v in violations if "secret_scrubber" in _norm_path(v[0], tmp_path) and v[2] == "placeholder"
    ]
    assert not scrubber_violations


def test_excluded_dirs_skipped(tmp_path: Path) -> None:
    _write_tree(
        tmp_path,
        {
            ".git/HEAD": "ref: refs/heads/main",
            ".venv/lib/foo.py": "raise NotImplementedError",
            "src/real.py": "raise NotImplementedError",
        },
    )
    violations = scan_root(tmp_path)
    rels = [_norm_path(p, tmp_path) for p, _, _ in violations]
    assert not any(".git" in r or ".venv" in r for r in rels)
    assert any("src/real.py" in r for r in rels)


def test_policy_placeholder_fails(tmp_path: Path) -> None:
    _write_tree(
        tmp_path,
        {
            "policy/security/foo.yaml": "# placeholder thresholds\n",
        },
    )
    violations = scan_root(tmp_path)
    rels = [_norm_path(p, tmp_path) for p, _, t in violations if t == "placeholder"]
    assert any("policy" in r for r in rels)


def test_mkdocs_checked(tmp_path: Path) -> None:
    _write_tree(tmp_path, {"mkdocs.yml": "docs: stub\n"})
    violations = scan_root(tmp_path)
    assert any("mkdocs.yml" in _norm_path(p, tmp_path) for p, _, _ in violations)


def test_github_excluded(tmp_path: Path) -> None:
    """Workflow step names may mention placeholder/stub; .github is excluded from scanning."""
    _write_tree(
        tmp_path,
        {".github/workflows/ci.yml": "steps:\n  - name: No placeholders / stubs gate\n"},
    )
    violations = scan_root(tmp_path)
    assert not violations


def test_clean_tree_no_violations(tmp_path: Path) -> None:
    _write_tree(
        tmp_path,
        {
            "docs/readme.md": "No markers here.\n",
            "src/foo.py": "def bar(): pass\n",
            "tests/test_ok.py": "class Helper:\n    pass\n",
        },
    )
    violations = scan_root(tmp_path)
    assert not violations
