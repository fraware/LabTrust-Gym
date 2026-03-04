"""
Validate uncertainty quantification mapping: every key in the mapping exists in the metrics contract or summary columns.
See docs/benchmarks/uncertainty_quantification.md and policy/benchmarks/uncertainty_metric_mapping.v0.1.json.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _allowed_metric_and_summary_keys() -> set[str]:
    """Return the set of metric/summary keys that are valid (episode.metrics or v0.3 summary base)."""
    from labtrust_gym.benchmarks.summarize import METRIC_KEYS

    allowed: set[str] = set()
    # Base metric keys (per-episode and summary)
    for key in METRIC_KEYS:
        allowed.add(key)
        allowed.add(f"{key}_mean")
        allowed.add(f"{key}_std")
        allowed.add(f"{key}_p50")
        allowed.add(f"{key}_p90")
        allowed.add(f"{key}_mean_ci_lower")
        allowed.add(f"{key}_mean_ci_upper")
    # v0.3-only summary keys
    allowed.add("containment_success_rate_ci_lower")
    allowed.add("containment_success_rate_ci_upper")
    allowed.add("llm_confidence_ece_mean")
    allowed.add("llm_confidence_mce_mean")
    # Per-episode optional metric (object)
    allowed.add("llm_confidence_calibration")
    return allowed


def test_uncertainty_mapping_keys_exist_in_contract() -> None:
    """Every key in uncertainty_metric_mapping.v0.1.json exists in metrics contract or summary columns."""
    repo = _repo_root()
    path = repo / "policy" / "benchmarks" / "uncertainty_metric_mapping.v0.1.json"
    if not path.exists():
        pytest.skip("policy/benchmarks/uncertainty_metric_mapping.v0.1.json not found")
    data = json.loads(path.read_text(encoding="utf-8"))
    mapping = data.get("mapping")
    if not isinstance(mapping, dict):
        pytest.skip("mapping not present or not a dict")
    allowed = _allowed_metric_and_summary_keys()
    for key, uncertainty_type in mapping.items():
        assert key in allowed, (
            f"Uncertainty mapping key {key!r} (type={uncertainty_type}) is not in allowed metrics/summary keys. "
            "Add it to the metrics contract or to _allowed_metric_and_summary_keys."
        )
        assert uncertainty_type in ("epistemic", "aleatoric"), (
            f"Uncertainty type for {key!r} must be 'epistemic' or 'aleatoric', got {uncertainty_type!r}"
        )


def test_uncertainty_report_script(tmp_path: Path) -> None:
    """uncertainty_report script on fixture run dir produces epistemic/aleatoric sections."""
    import subprocess
    import sys

    (tmp_path / "summary").mkdir()
    summary_csv = tmp_path / "summary" / "summary_coord.csv"
    summary_csv.write_text(
        "method_id,scale_id,containment_success_rate_ci_lower,llm_confidence_ece_mean\nm1,s1,0.8,0.1\n",
        encoding="utf-8",
    )
    repo = _repo_root()
    script = repo / "scripts" / "uncertainty_report.py"
    if not script.exists():
        pytest.skip("scripts/uncertainty_report.py not found")
    result = subprocess.run(
        [sys.executable, str(script), "--run", str(tmp_path), "--policy-root", str(repo)],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    out = result.stdout
    assert "Epistemic" in out
    assert "Aleatoric" in out


def test_uncertainty_report_gate_passes(tmp_path: Path) -> None:
    """Uncertainty report with --gate when values satisfy thresholds exits 0."""
    import subprocess
    import sys

    (tmp_path / "summary").mkdir()
    (tmp_path / "summary" / "summary_coord.csv").write_text(
        "method_id,llm_confidence_ece_mean\nm1,0.05\n",
        encoding="utf-8",
    )
    gate = tmp_path / "gate.yaml"
    gate.write_text(
        "thresholds:\n  epistemic:\n    llm_confidence_ece_mean: { max: 0.1 }\n",
        encoding="utf-8",
    )
    repo = _repo_root()
    script = repo / "scripts" / "uncertainty_report.py"
    if not script.exists():
        pytest.skip("scripts/uncertainty_report.py not found")
    result = subprocess.run(
        [sys.executable, str(script), "--run", str(tmp_path), "--policy-root", str(repo), "--gate", str(gate)],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_uncertainty_report_gate_fails(tmp_path: Path) -> None:
    """Uncertainty report with --gate when a value violates threshold exits 1."""
    import subprocess
    import sys

    (tmp_path / "summary").mkdir()
    (tmp_path / "summary" / "summary_coord.csv").write_text(
        "method_id,llm_confidence_ece_mean\nm1,0.15\n",
        encoding="utf-8",
    )
    gate = tmp_path / "gate.yaml"
    gate.write_text(
        "thresholds:\n  epistemic:\n    llm_confidence_ece_mean: { max: 0.1 }\n",
        encoding="utf-8",
    )
    repo = _repo_root()
    script = repo / "scripts" / "uncertainty_report.py"
    if not script.exists():
        pytest.skip("scripts/uncertainty_report.py not found")
    result = subprocess.run(
        [sys.executable, str(script), "--run", str(tmp_path), "--policy-root", str(repo), "--gate", str(gate)],
        capture_output=True,
        text=True,
        cwd=repo,
    )
    assert result.returncode == 1, "expected exit 1 on gate violation"
    assert "Gate violations" in result.stdout or "llm_confidence_ece_mean" in result.stdout
