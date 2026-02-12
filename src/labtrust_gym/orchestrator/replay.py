"""
Replay mode: load a recorded run, re-execute deterministically, and compare
receipts digests, policy gate results, and tool calls. Produces replay_summary.json
with status (ok | diverged | failed), first_divergence_step, and diff artifacts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from labtrust_gym.export.receipts import (
    load_episode_log,
    build_receipts_from_log,
)


def _canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True)


def _normalize_violations(entry: dict[str, Any]) -> list[tuple[str, str]]:
    """Normalize violations to comparable (invariant_id, status) tuples, sorted."""
    out: list[tuple[str, str]] = []
    for v in entry.get("violations") or []:
        inv = v.get("invariant_id") or ""
        st = (v.get("status") or "").upper()
        if inv or st:
            out.append((inv, st))
    return sorted(out)


def _step_comparable(entry: dict[str, Any]) -> dict[str, Any]:
    """Extract comparable fields for one step (policy gate, tool call)."""
    return {
        "t_s": entry.get("t_s"),
        "agent_id": entry.get("agent_id"),
        "action_type": entry.get("action_type"),
        "status": entry.get("status"),
        "blocked_reason_code": entry.get("blocked_reason_code"),
        "violations": _normalize_violations(entry),
        "hashchain_head": (entry.get("hashchain") or {}).get("head_hash"),
        "emits": sorted(entry.get("emits") or []),
    }


def _receipts_digest(entries: list[dict[str, Any]]) -> str:
    """Deterministic digest of receipts built from log (for comparison)."""
    try:
        receipts = build_receipts_from_log(entries)
        return hashlib.sha256(_canonical_json(receipts).encode("utf-8")).hexdigest()
    except Exception:
        return ""


def compare_episode_logs(
    ref_entries: list[dict[str, Any]],
    run_entries: list[dict[str, Any]],
    compare_receipt_digests: bool = True,
) -> dict[str, Any]:
    """
    Compare reference and re-run episode logs step-by-step.

    Returns dict with:
      - status: "ok" | "diverged" | "failed"
      - first_divergence_step: int | None
      - steps_compared: int
      - diffs: list of {step_index, field, expected, actual}
      - receipt_digests_match: bool (if compare_receipt_digests)
      - ref_receipt_digest, run_receipt_digest: str (when comparing digests)
    """
    diffs: list[dict[str, Any]] = []
    first_divergence_step: int | None = None
    steps_compared = min(len(ref_entries), len(run_entries))

    if len(ref_entries) != len(run_entries):
        diffs.append({
            "step_index": None,
            "field": "step_count",
            "expected": len(ref_entries),
            "actual": len(run_entries),
        })
        first_divergence_step = steps_compared

    for i in range(steps_compared):
        ref_c = _step_comparable(ref_entries[i])
        run_c = _step_comparable(run_entries[i])
        for key in ref_c:
            if key not in run_c:
                continue
            ev = ref_c[key]
            av = run_c[key]
            if ev != av:
                diffs.append({
                    "step_index": i,
                    "field": key,
                    "expected": ev,
                    "actual": av,
                })
                if first_divergence_step is None:
                    first_divergence_step = i

    receipt_match = True
    ref_digest = ""
    run_digest = ""
    if compare_receipt_digests and ref_entries and run_entries:
        ref_digest = _receipts_digest(ref_entries)
        run_digest = _receipts_digest(run_entries)
        receipt_match = ref_digest == run_digest
        if not receipt_match and first_divergence_step is None and not diffs:
            first_divergence_step = steps_compared
        if not receipt_match:
            diffs.append({
                "step_index": None,
                "field": "receipt_digest",
                "expected": ref_digest,
                "actual": run_digest,
            })

    status = "failed" if (ref_entries and not run_entries) else (
        "ok" if not diffs else "diverged"
    )

    out: dict[str, Any] = {
        "status": status,
        "first_divergence_step": first_divergence_step,
        "steps_compared": steps_compared,
        "diffs": diffs,
    }
    if compare_receipt_digests:
        out["receipt_digests_match"] = receipt_match
        out["ref_receipt_digest"] = ref_digest
        out["run_receipt_digest"] = run_digest
    return out


def _find_reference_log(recorded_run_dir: Path) -> Path | None:
    """Locate episode log in recorded run dir (episode_log.jsonl or episode_0.jsonl)."""
    for name in ("episode_log.jsonl", "episode_0.jsonl"):
        p = recorded_run_dir / name
        if p.exists():
            return p
    return None


def _load_results_json(recorded_run_dir: Path) -> dict[str, Any] | None:
    """Load results.json from run dir for re-run config."""
    p = recorded_run_dir / "results.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _re_execute_episode(
    results: dict[str, Any],
    out_dir: Path,
    policy_root: Path,
) -> Path | None:
    """Run one episode with config from results.json; return path to episode log."""
    task_name = results.get("task")
    seeds = results.get("seeds")
    config = results.get("config") or {}
    if not task_name or not seeds:
        return None
    seed = int(seeds[0])
    coord_method = config.get("coord_method")
    out_dir.mkdir(parents=True, exist_ok=True)
    replay_log = out_dir / "episode_log_replay.jsonl"
    replay_results = out_dir / "results_replay.json"
    try:
        from labtrust_gym.benchmarks.runner import run_benchmark

        run_benchmark(
            task_name=task_name,
            num_episodes=1,
            base_seed=seed,
            out_path=replay_results,
            log_path=replay_log,
            repo_root=policy_root,
            coord_method=coord_method,
            timing_mode=config.get("timing_mode"),
        )
        return replay_log if replay_log.exists() else None
    except Exception:
        return None


def run_replay(
    episode_log_path: Path | None = None,
    method_ids: list[str] | None = None,
    out_dir: Path | None = None,
    policy_root: Path | None = None,
    recorded_run_dir: Path | None = None,
    re_run_episode_log_path: Path | None = None,
) -> dict[str, Any]:
    """
    Load a recorded run, optionally re-execute, and compare.

    Call either:
      - recorded_run_dir + out_dir + policy_root: load reference from
        recorded_run_dir (episode_log.jsonl or episode_0.jsonl), re-run one
        episode using results.json in recorded_run_dir, compare, write
        replay_summary.json to out_dir.
      - episode_log_path (reference) + re_run_episode_log_path (re-run) + out_dir:
        compare two logs and write replay_summary.json.

    method_ids: reserved for future per-method comparison; currently one re-run.
    Returns dict with replay_run_dir, method_comparisons, summary_path, status,
    first_divergence_step, diff_summary, artifact_pointers (no sentinel status).
    """
    out_dir = Path(out_dir or ".").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    policy_root = Path(policy_root or ".").resolve()

    ref_entries: list[dict[str, Any]] = []
    run_entries: list[dict[str, Any]] = []
    ref_log_path: Path | None = None
    run_log_path: Path | None = None

    if episode_log_path is not None:
        ref_log_path = Path(episode_log_path).resolve()
        ref_entries = load_episode_log(ref_log_path)
    if recorded_run_dir is not None:
        recorded_run_dir = Path(recorded_run_dir).resolve()
        if not ref_log_path:
            ref_log_path = _find_reference_log(recorded_run_dir)
            if ref_log_path is not None:
                ref_entries = load_episode_log(ref_log_path)

    if re_run_episode_log_path is not None:
        run_log_path = Path(re_run_episode_log_path).resolve()
        run_entries = load_episode_log(run_log_path)
    elif recorded_run_dir is not None:
        results = _load_results_json(Path(recorded_run_dir))
        if results:
            run_log_path = _re_execute_episode(results, out_dir, policy_root)
            if run_log_path is not None:
                run_entries = load_episode_log(run_log_path)

    comparison = compare_episode_logs(ref_entries, run_entries)
    artifact_pointers: dict[str, Any] = {
        "reference_log": str(ref_log_path) if ref_log_path else None,
        "re_run_log": str(run_log_path) if run_log_path else None,
    }
    if recorded_run_dir is not None:
        artifact_pointers["recorded_run_dir"] = str(Path(recorded_run_dir).resolve())

    summary = {
        "status": comparison["status"],
        "first_divergence_step": comparison["first_divergence_step"],
        "steps_compared": comparison["steps_compared"],
        "diff_summary": comparison["diffs"],
        "receipt_digests_match": comparison.get("receipt_digests_match"),
        "artifact_pointers": artifact_pointers,
        "method_ids": method_ids or [],
        "method_comparisons": [],
    }
    summary_path = out_dir / "replay_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return {
        "replay_run_dir": str(out_dir),
        "method_comparisons": summary["method_comparisons"],
        "summary_path": str(summary_path),
        "status": comparison["status"],
        "first_divergence_step": comparison["first_divergence_step"],
        "diff_summary": comparison["diffs"],
        "artifact_pointers": artifact_pointers,
    }
