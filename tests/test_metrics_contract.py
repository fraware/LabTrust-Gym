"""
Enforce metrics contract between results.v0.2 and results.v0.3.

- v0.2 remains CI-stable, minimal, semantically frozen.
- v0.3 adds paper-grade fields without breaking v0.2 semantics.
- Schema compatibility: every v0.2 top-level and episode.metrics field exists in v0.3 with compatible types.
- Summarize-results output: summary_v0.2.csv (mean/std only), summary_v0.3.csv (may have NaNs), summary.md from v0.2 only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_schema(version: str) -> dict:
    repo = _repo_root()
    path = repo / "policy" / "schemas" / f"results.v0.{version}.schema.json"
    if not path.exists():
        pytest.skip(f"policy/schemas/results.v0.{version}.schema.json not found")
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_type_set(node: dict) -> set[str]:
    """Return set of JSON Schema types for a node (type may be string or array)."""
    t = node.get("type")
    if t is None:
        if "const" in node:
            return {"string"} if isinstance(node["const"], str) else {"number", "integer"}
        return set()
    if isinstance(t, str):
        return {t}
    if isinstance(t, list):
        return set(t)
    return set()


def _types_compatible(v2_type: set[str], v3_type: set[str]) -> bool:
    """True if v0.2 type is compatible with v0.3 (same or v3 allows v2)."""
    if not v2_type or not v3_type:
        return True
    if v2_type == v3_type:
        return True
    if "null" in v2_type and "null" not in v3_type:
        v2_without_null = v2_type - {"null"}
        return v2_without_null <= v3_type
    return v2_type <= v3_type


def _property_keys(schema: dict, path: list[str]) -> set[str]:
    """Get required + properties keys at path (e.g. [] for root, ['episodes','items','properties','metrics','properties'] for metrics)."""
    node = schema
    for key in path:
        node = node.get(key)
        if node is None:
            return set()
    required = set(node.get("required", []))
    props = set(node.get("properties", {}).keys())
    return required | props


def _get_property_schema(schema: dict, path: list[str], key: str) -> dict | None:
    """Get the schema for a property at path (e.g. path=['episodes','items','properties','metrics','properties'], key='throughput')."""
    node = schema
    for k in path:
        node = node.get(k)
        if node is None:
            return None
    return (node.get("properties") or {}).get(key)


def test_results_v02_v03_schema_compatibility_top_level() -> None:
    """Every v0.2 top-level field exists in v0.3 with compatible types."""
    v2 = _load_schema("2")
    v3 = _load_schema("3")
    v2_keys = set(v2.get("required", [])) | set((v2.get("properties") or {}).keys())
    v3_keys = set(v3.get("required", [])) | set((v3.get("properties") or {}).keys())
    missing = v2_keys - v3_keys
    assert not missing, f"v0.3 missing top-level fields from v0.2: {missing}"
    for key in v2_keys:
        p2 = (v2.get("properties") or {}).get(key)
        p3 = (v3.get("properties") or {}).get(key)
        if p2 is None or p3 is None:
            continue
        t2 = _schema_type_set(p2)
        t3 = _schema_type_set(p3)
        assert _types_compatible(t2, t3), f"v0.2 top-level field {key!r}: type {t2} not compatible with v0.3 type {t3}"


def test_results_v02_v03_schema_compatibility_episode_metrics() -> None:
    """Every v0.2 episode.metrics field exists in v0.3 with compatible types."""
    v2 = _load_schema("2")
    v3 = _load_schema("3")
    path = ["episodes", "items", "properties", "metrics", "properties"]
    v2_metric_keys = _property_keys(v2, path)
    v3_metric_keys = _property_keys(v3, path)
    missing = v2_metric_keys - v3_metric_keys
    assert not missing, f"v0.3 episode.metrics missing fields from v0.2: {missing}"
    for key in v2_metric_keys:
        p2 = _get_property_schema(v2, path, key)
        p3 = _get_property_schema(v3, path, key)
        if p2 is None or p3 is None:
            continue
        t2 = _schema_type_set(p2)
        t3 = _schema_type_set(p3)
        assert _types_compatible(t2, t3), (
            f"v0.2 episode.metrics field {key!r}: type {t2} not compatible with v0.3 type {t3}"
        )


# Minimal v0.2-valid results fixture for summarize-results tests.
FIXTURE_RESULTS_V02 = {
    "schema_version": "0.2",
    "task": "TaskA",
    "seeds": [10, 11],
    "episodes": [
        {"seed": 10, "metrics": {"throughput": 4, "steps": 80, "holds_count": 0}},
        {"seed": 11, "metrics": {"throughput": 5, "steps": 82, "holds_count": 0}},
    ],
    "agent_baseline_id": "scripted_ops_v1",
    "policy_fingerprint": None,
    "partner_id": None,
    "git_sha": "fixture",
}


def test_summarize_results_output_files(tmp_path: Path) -> None:
    """Run summarize-results on a small fixture; assert output files and semantics."""
    from labtrust_gym.benchmarks.summarize import run_summarize

    fixture_path = tmp_path / "results.json"
    fixture_path.write_text(json.dumps(FIXTURE_RESULTS_V02), encoding="utf-8")
    out_dir = tmp_path / "out"
    run_summarize([fixture_path], out_dir, out_basename="summary")

    # summary_v0.2.csv exists and has mean/std columns only (no quantile/CI columns)
    v02_csv = out_dir / "summary_v0.2.csv"
    assert v02_csv.exists(), "summary_v0.2.csv must exist"
    v02_header = v02_csv.read_text(encoding="utf-8").split("\n")[0]
    v02_columns = [c.strip('"') for c in v02_header.split(",")]
    paper_only = [c for c in v02_columns if "_p50" in c or "_p90" in c or "mean_ci_lower" in c or "mean_ci_upper" in c]
    assert not paper_only, f"summary_v0.2.csv must not contain paper-grade columns: {paper_only}"
    assert any("_mean" in c for c in v02_columns), "summary_v0.2.csv should have *_mean columns"
    assert any("_std" in c for c in v02_columns), "summary_v0.2.csv should have *_std columns"

    # summary_v0.3.csv exists (may have NaNs for quantiles/CI if not present)
    v03_csv = out_dir / "summary_v0.3.csv"
    assert v03_csv.exists(), "summary_v0.3.csv must exist"
    v03_content = v03_csv.read_text(encoding="utf-8")
    assert "task" in v03_content or "n_episodes" in v03_content

    # summary.md is derived from v0.2 fields only (no quantile column names in header)
    md_path = out_dir / "summary.md"
    assert md_path.exists(), "summary.md must exist"
    md_lines = md_path.read_text(encoding="utf-8").strip().split("\n")
    assert len(md_lines) >= 2, "summary.md must have header and separator"
    md_header = md_lines[0]
    assert "_p50" not in md_header and "_p90" not in md_header, (
        "summary.md must not contain quantile columns (v0.2-only)"
    )
    assert "mean_ci_lower" not in md_header and "mean_ci_upper" not in md_header, (
        "summary.md must not contain CI columns (v0.2-only)"
    )

    # summary.csv exists (copy of v0.2)
    summary_csv = out_dir / "summary.csv"
    assert summary_csv.exists(), "summary.csv must exist"
    assert summary_csv.read_text(encoding="utf-8") == v02_csv.read_text(encoding="utf-8"), (
        "summary.csv must equal summary_v0.2.csv"
    )


def test_summarize_results_v02_csv_mean_std_only(tmp_path: Path) -> None:
    """summary_v0.2.csv contains only mean/std style aggregates, no quantiles or CI."""
    from labtrust_gym.benchmarks.summarize import (
        load_results_from_path,
        rows_to_csv,
        summarize_results,
    )

    fixture_path = tmp_path / "r.json"
    fixture_path.write_text(json.dumps(FIXTURE_RESULTS_V02), encoding="utf-8")
    loaded = load_results_from_path(fixture_path)
    assert loaded
    rows = summarize_results(loaded)
    assert rows
    csv_text = rows_to_csv(rows)
    header = csv_text.split("\n")[0]
    cols = [c.strip('"') for c in header.split(",")]
    for c in cols:
        if c in ("task", "agent_baseline_id", "partner_id", "n_episodes"):
            continue
        assert c.endswith("_mean") or c.endswith("_std"), f"v0.2 summary column must be *_mean or *_std: {c}"
