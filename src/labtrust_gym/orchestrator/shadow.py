"""
Shadow mode: compute coordination actions without executing them; compare with
executed baseline. Used for safe validation and drift detection.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def run_shadow(
    baseline_run_dir: Path,
    shadow_method_id: str,
    out_dir: Path,
    policy_root: Path,
    compare_metric: str = "action_index",
) -> dict[str, Any]:
    """
    Load baseline episode log (or results) from baseline_run_dir; for each step,
    run shadow_method_id to compute proposed actions. Do not execute; record
    proposed vs baseline (executed) actions. Write comparison to out_dir.

    Returns dict with shadow_run_dir, comparison_path, drift_summary.
    """
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    comparison_path = out_dir / "shadow_comparison.jsonl"
    comparison_path.write_text("", encoding="utf-8")
    return {
        "shadow_run_dir": str(out_dir),
        "comparison_path": str(comparison_path),
        "drift_summary": {"steps_compared": 0, "steps_differed": 0},
        "status": "stub",
    }
