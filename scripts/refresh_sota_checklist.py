"""
Regenerate the SOTA (state of the art) refinement dashboard table.

Reads conformance_config.yaml, strictly-better tests per method,
coordination_methods.v0.1.yaml, and method module docstrings (Envelope
audit) to output a markdown table. Run from repo root:
  python scripts/refresh_sota_checklist.py
"""

from __future__ import annotations

import re
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_yaml(path: Path) -> dict:
    try:
        import yaml
        with path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def _method_ids_from_policy(repo: Path) -> list[str]:
    path = repo / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
    if not path.exists():
        return []
    data = _load_yaml(path)
    methods = (data.get("coordination_methods") or {}).get("methods") or []
    ids = []
    for entry in methods:
        if isinstance(entry, dict) and entry.get("method_id"):
            ids.append(entry["method_id"])
    return sorted(ids)


def _pass_budget_evidence(repo: Path) -> tuple[set[str], set[str]]:
    path = repo / "tests" / "coord_methods" / "conformance" / "conformance_config.yaml"
    if not path.exists():
        return set(), set()
    cfg = _load_yaml(path)
    return (
        set(cfg.get("pass_budget") or []),
        set(cfg.get("pass_evidence") or []),
    )


def _envelope_yaml_method_ids_simple(repo: Path) -> set[str]:
    """Methods that have # compute_envelope in their YAML block."""
    path = repo / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
    if not path.exists():
        return set()
    lines = path.read_text(encoding="utf-8").split("\n")
    ids = set()
    current_id = None
    for i, line in enumerate(lines):
        method_match = re.match(r'\s*-\s*method_id:\s*"([^"]+)"', line)
        if method_match:
            current_id = method_match.group(1)
        if current_id and "compute_envelope" in line:
            ids.add(current_id)
        # Reset when we hit the next top-level list item (new method block)
        if re.match(r'^\s*-\s*method_id:', line) and i > 0 and current_id:
            # Keep current_id for this line; we just set it above
            pass
    return ids


def _envelope_docstring_method_ids_grep(repo: Path) -> set[str]:
    base = repo / "src" / "labtrust_gym" / "baselines" / "coordination"
    if not base.exists():
        return set()
    ids = set()
    for py in base.rglob("*.py"):
        if "__pycache__" in str(py):
            continue
        try:
            if "Envelope (SOTA audit)" in py.read_text(encoding="utf-8"):
                stem = py.stem
                if stem == "detector_advisor":
                    ids.add("llm_detector_throttle_advisor")
                elif stem == "hierarchical_method":
                    ids.add("hierarchical_hub_local")
                else:
                    ids.add(stem)
        except Exception:
            continue
    return ids


def _strictly_better_from_test_names(repo: Path, all_method_ids: list[str]) -> set[str]:
    path = repo / "tests" / "test_coord_strictly_better.py"
    if not path.exists():
        return set()
    text = path.read_text(encoding="utf-8")
    runs = re.findall(r'coord_method="([^"]+)"', text)
    # Each test runs baseline then variant; the variant is the method we assert as >= baseline
    found = set()
    for i in range(1, len(runs), 2):
        if i < len(runs):
            found.add(runs[i])
    return found


def main() -> None:
    repo = _repo_root()
    pass_budget, pass_evidence = _pass_budget_evidence(repo)
    method_ids = _method_ids_from_policy(repo)
    strictly_better = _strictly_better_from_test_names(repo, method_ids)
    envelope_yaml = _envelope_yaml_method_ids_simple(repo)
    envelope_doc = _envelope_docstring_method_ids_grep(repo)

    # Build rows: only include method_ids that appear in policy (optionally filter to a subset)
    rows = []
    for mid in method_ids:
        row = (
            mid,
            "Y" if mid in pass_budget else "N",
            "Y" if mid in pass_evidence else "N",
            "Y" if mid in strictly_better else "N",
            "Y" if mid in envelope_yaml else "N",
            "Y" if mid in envelope_doc else "N",
        )
        rows.append(row)

    # Print markdown table
    print("| method_id | pass_budget | pass_evidence | strictly_better_test | envelope_yaml | envelope_docstring |")
    print("|-----------|-------------|---------------|------------------------|---------------|---------------------|")
    for r in rows:
        print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} | {r[4]} | {r[5]} |")


if __name__ == "__main__":
    main()
