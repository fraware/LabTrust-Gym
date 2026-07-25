"""
Replay mode: load a recorded run or action sequence, re-execute deterministically,
and compare state transitions, reason codes, canonical episode logs, and evidence
digests. Produces replay_summary.json with status (ok | diverged | failed),
first_divergence_step, and diff artifacts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from labtrust_gym.export.receipts import (
    build_receipts_from_log,
    load_episode_log,
)
from labtrust_gym.util.json_utils import canonical_json


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
    """Extract comparable fields for one step (policy gate, tool call, reason codes)."""
    return {
        "t_s": entry.get("t_s"),
        "agent_id": entry.get("agent_id"),
        "action_type": entry.get("action_type"),
        "status": entry.get("status"),
        "blocked_reason_code": entry.get("blocked_reason_code"),
        "violations": _normalize_violations(entry),
        "hashchain_head": (entry.get("hashchain") or {}).get("head_hash")
        or entry.get("hashchain_head"),
        "emits": sorted(entry.get("emits") or []),
    }


def canonical_episode_log_digest(entries: list[dict[str, Any]]) -> str:
    """SHA-256 of canonical JSON of per-step comparable fields (exact-match contract)."""
    payload = [_step_comparable(e) for e in entries]
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def evidence_digest(entries: list[dict[str, Any]]) -> str:
    """
    Deterministic evidence digest: receipts bundle payload when buildable,
    else canonical episode log digest.
    """
    try:
        receipts = build_receipts_from_log(entries)
        if receipts:
            return hashlib.sha256(canonical_json(receipts).encode("utf-8")).hexdigest()
    except Exception:
        pass
    return canonical_episode_log_digest(entries)


def _receipts_digest(entries: list[dict[str, Any]]) -> str:
    """Deterministic digest of receipts built from log (for comparison)."""
    try:
        receipts = build_receipts_from_log(entries)
        return hashlib.sha256(canonical_json(receipts).encode("utf-8")).hexdigest()
    except Exception:
        return ""


def compare_episode_logs(
    ref_entries: list[dict[str, Any]],
    run_entries: list[dict[str, Any]],
    compare_receipt_digests: bool = True,
    compare_canonical_log: bool = True,
    compare_evidence: bool = True,
) -> dict[str, Any]:
    """
    Compare reference and re-run episode logs step-by-step.

    Exact-match default: statuses, reason codes, hashchain heads, emits, and
    digests must be identical (no float tolerance).

    Returns dict with:
      - status: "ok" | "diverged" | "failed"
      - first_divergence_step: int | None
      - steps_compared: int
      - diffs: list of {step_index, field, expected, actual}
      - receipt_digests_match / canonical_episode_log_digests_match /
        evidence_digests_match when enabled
    """
    diffs: list[dict[str, Any]] = []
    first_divergence_step: int | None = None
    steps_compared = min(len(ref_entries), len(run_entries))

    if len(ref_entries) != len(run_entries):
        diffs.append(
            {
                "step_index": None,
                "field": "step_count",
                "expected": len(ref_entries),
                "actual": len(run_entries),
            }
        )
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
                diffs.append(
                    {
                        "step_index": i,
                        "field": key,
                        "expected": ev,
                        "actual": av,
                    }
                )
                if first_divergence_step is None:
                    first_divergence_step = i

    def _note_digest(field: str, expected: str, actual: str) -> bool:
        nonlocal first_divergence_step
        if expected == actual:
            return True
        diffs.append(
            {
                "step_index": None,
                "field": field,
                "expected": expected,
                "actual": actual,
            }
        )
        if first_divergence_step is None:
            first_divergence_step = steps_compared
        return False

    receipt_match = True
    ref_digest = ""
    run_digest = ""
    if compare_receipt_digests and ref_entries and run_entries:
        ref_digest = _receipts_digest(ref_entries)
        run_digest = _receipts_digest(run_entries)
        receipt_match = _note_digest("receipt_digest", ref_digest, run_digest)

    ref_canon = ""
    run_canon = ""
    canon_match = True
    if compare_canonical_log and ref_entries and run_entries:
        ref_canon = canonical_episode_log_digest(ref_entries)
        run_canon = canonical_episode_log_digest(run_entries)
        canon_match = _note_digest("canonical_episode_log_digest", ref_canon, run_canon)

    ref_evidence = ""
    run_evidence = ""
    evidence_match = True
    if compare_evidence and ref_entries and run_entries:
        ref_evidence = evidence_digest(ref_entries)
        run_evidence = evidence_digest(run_entries)
        evidence_match = _note_digest("evidence_digest", ref_evidence, run_evidence)

    status = "failed" if (ref_entries and not run_entries) else ("ok" if not diffs else "diverged")

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
    if compare_canonical_log:
        out["canonical_episode_log_digests_match"] = canon_match
        out["ref_canonical_episode_log_digest"] = ref_canon
        out["run_canonical_episode_log_digest"] = run_canon
    if compare_evidence:
        out["evidence_digests_match"] = evidence_match
        out["ref_evidence_digest"] = ref_evidence
        out["run_evidence_digest"] = run_evidence
    return out


def _find_reference_log(recorded_run_dir: Path) -> Path | None:
    """Locate episode log in recorded run dir (episode_log.jsonl or episode_0.jsonl)."""
    for name in ("episode_log.jsonl", "episode_0.jsonl", "episodes.jsonl"):
        p = recorded_run_dir / name
        if p.exists():
            return p
    # Nested logs/episode_*.jsonl
    logs = recorded_run_dir / "logs"
    if logs.is_dir():
        for name in ("episode_log.jsonl", "episode_0.jsonl", "episodes.jsonl"):
            p = logs / name
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


def load_action_sequence(path: Path) -> dict[str, Any]:
    """
    Load a recorded action sequence JSON.

    Schema::
      {
        "seed": 42,
        "num_runners": 1,
        "dt_s": 10,
        "steps": [
          {"ops_0": 0, "runner_0": 1, ...},
          ...
        ],
        "action_infos": [  // optional, parallel to steps
          {"ops_0": {"device_id": "..."}, ...},
          ...
        ]
      }
    """
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "steps" not in data:
        raise ValueError("action sequence must be a JSON object with a 'steps' list")
    if not isinstance(data["steps"], list):
        raise ValueError("'steps' must be a list of per-step action dicts")
    return data


def replay_action_sequence(
    action_sequence: dict[str, Any] | Path,
    out_log_path: Path,
    *,
    seed: int | None = None,
    num_runners: int | None = None,
) -> list[dict[str, Any]]:
    """
    Re-execute a Parallel env action sequence and write an episode log.

    Returns loaded episode log entries after close.
    """
    if isinstance(action_sequence, Path | str):
        action_sequence = load_action_sequence(Path(action_sequence))
    seq = action_sequence
    steps = list(seq.get("steps") or [])
    infos_list = list(seq.get("action_infos") or [])
    use_seed = int(seed if seed is not None else seq.get("seed", 0))
    runners = int(num_runners if num_runners is not None else seq.get("num_runners", 2))
    dt_s = int(seq.get("dt_s", 10))

    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    out_log_path = Path(out_log_path)
    out_log_path.parent.mkdir(parents=True, exist_ok=True)
    if out_log_path.exists():
        out_log_path.unlink()

    env = LabTrustParallelEnv(num_runners=runners, dt_s=dt_s, log_path=out_log_path)
    try:
        env.reset(seed=use_seed)
        for i, actions in enumerate(steps):
            if not isinstance(actions, dict):
                raise ValueError(f"step {i} actions must be a dict agent->int")
            action_infos = infos_list[i] if i < len(infos_list) else None
            env.step(actions, action_infos=action_infos)
    finally:
        env.close()

    return load_episode_log(out_log_path) if out_log_path.exists() else []


def _write_summary(
    out_dir: Path,
    comparison: dict[str, Any],
    artifact_pointers: dict[str, Any],
    method_ids: list[str] | None = None,
) -> dict[str, Any]:
    summary = {
        "status": comparison["status"],
        "first_divergence_step": comparison["first_divergence_step"],
        "steps_compared": comparison["steps_compared"],
        "diff_summary": comparison["diffs"],
        "receipt_digests_match": comparison.get("receipt_digests_match"),
        "canonical_episode_log_digests_match": comparison.get(
            "canonical_episode_log_digests_match"
        ),
        "evidence_digests_match": comparison.get("evidence_digests_match"),
        "ref_canonical_episode_log_digest": comparison.get("ref_canonical_episode_log_digest"),
        "run_canonical_episode_log_digest": comparison.get("run_canonical_episode_log_digest"),
        "ref_evidence_digest": comparison.get("ref_evidence_digest"),
        "run_evidence_digest": comparison.get("run_evidence_digest"),
        "artifact_pointers": artifact_pointers,
        "method_ids": method_ids or [],
        "method_comparisons": [],
        "match_mode": "exact",
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
        "comparison": comparison,
    }


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

    return _write_summary(out_dir, comparison, artifact_pointers, method_ids=method_ids)


def run_trajectory_replay(
    *,
    out_dir: Path,
    policy_root: Path | None = None,
    recorded_run_dir: Path | None = None,
    episode_log_path: Path | None = None,
    compare_log_path: Path | None = None,
    actions_path: Path | None = None,
    seed: int | None = None,
    num_runners: int | None = None,
) -> dict[str, Any]:
    """
    First-class trajectory replay entry point used by the CLI.

    Modes (exactly one primary input):
      1. --recorded-run DIR: re-run episode from results.json, compare to recorded log
      2. --episode-log PATH --compare-log PATH: compare two existing logs
      3. --actions PATH: re-execute Parallel action sequence; optionally compare to
         --episode-log as reference

    Diffs state transitions, blocked_reason_code, canonical episode log digest,
    and evidence digest under exact-match semantics.
    """
    out_dir = Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    policy_root = Path(policy_root or ".").resolve()

    if recorded_run_dir is not None:
        return run_replay(
            recorded_run_dir=Path(recorded_run_dir),
            out_dir=out_dir,
            policy_root=policy_root,
        )

    if actions_path is not None:
        replay_log = out_dir / "episode_log_replay.jsonl"
        run_entries = replay_action_sequence(
            Path(actions_path),
            replay_log,
            seed=seed,
            num_runners=num_runners,
        )
        ref_entries: list[dict[str, Any]] = []
        ref_log: Path | None = None
        if episode_log_path is not None:
            ref_log = Path(episode_log_path).resolve()
            ref_entries = load_episode_log(ref_log)
        elif not run_entries:
            comparison = {
                "status": "failed",
                "first_divergence_step": None,
                "steps_compared": 0,
                "diffs": [
                    {
                        "step_index": None,
                        "field": "replay",
                        "expected": "non-empty log",
                        "actual": "empty",
                    }
                ],
            }
            return _write_summary(
                out_dir,
                comparison,
                {
                    "actions_path": str(Path(actions_path).resolve()),
                    "re_run_log": str(replay_log),
                },
            )
        else:
            # Self-check: replay twice and compare (no external reference)
            replay_log_b = out_dir / "episode_log_replay_b.jsonl"
            ref_entries = replay_action_sequence(
                Path(actions_path),
                replay_log_b,
                seed=seed,
                num_runners=num_runners,
            )
            ref_log = replay_log_b
            run_entries = load_episode_log(replay_log)

        comparison = compare_episode_logs(ref_entries, run_entries)
        return _write_summary(
            out_dir,
            comparison,
            {
                "actions_path": str(Path(actions_path).resolve()),
                "reference_log": str(ref_log) if ref_log else None,
                "re_run_log": str(replay_log),
            },
        )

    if episode_log_path is not None and compare_log_path is not None:
        return run_replay(
            episode_log_path=Path(episode_log_path),
            re_run_episode_log_path=Path(compare_log_path),
            out_dir=out_dir,
            policy_root=policy_root,
        )

    raise ValueError(
        "Provide --recorded-run, or --actions, or both --episode-log and --compare-log"
    )
