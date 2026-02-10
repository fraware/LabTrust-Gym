"""
Replay mode: run the same episode log (obs/actions from a previous run) through
multiple coordination methods to compare "what would have happened". Critical for
review and debugging.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def run_replay(
    episode_log_path: Path,
    method_ids: list[str],
    out_dir: Path,
    policy_root: Path,
) -> dict[str, Any]:
    """
    Load episode log (obs sequence and optionally baseline actions) from
    episode_log_path. For each method_id in method_ids, re-run the method
    on the same obs sequence and record proposed actions (and optionally
    outcomes if env is deterministic). Write per-method comparison to out_dir.

    Returns dict with replay_run_dir, method_comparisons, summary_path.
    """
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "replay_summary.json"
    summary_path.write_text(
        '{"method_ids": [], "comparisons": [], "status": "stub"}',
        encoding="utf-8",
    )
    return {
        "replay_run_dir": str(out_dir),
        "method_comparisons": [],
        "summary_path": str(summary_path),
        "status": "stub",
    }
