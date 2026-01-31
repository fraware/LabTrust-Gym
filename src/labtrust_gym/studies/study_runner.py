"""
Research-grade study runner: expands Cartesian product of ablations,
runs benchmark per condition with deterministic seeds, writes reproducible
artifact dir.

Output layout:
  out_dir/
    manifest.json
    conditions.jsonl
    results/<condition_id>/results.json
    logs/<condition_id>/episodes.jsonl
"""

from __future__ import annotations

import hashlib
import itertools
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from labtrust_gym.benchmarks.runner import run_benchmark


def _git_commit_hash(cwd: Optional[Path] = None) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=cwd or Path.cwd(),
        )
        if out.returncode == 0 and out.stdout:
            return out.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _policy_versions(root: Path) -> Dict[str, str]:
    versions: Dict[str, str] = {}
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if emits_path.exists():
        try:
            data = emits_path.read_text(encoding="utf-8")
            for line in data.splitlines()[:20]:
                if "version:" in line:
                    raw = line.split("version:")[-1].strip().strip('"')
                    versions["emits_vocab"] = raw
                    break
        except Exception:
            versions["emits_vocab"] = "unknown"
    return versions


def _python_version() -> str:
    return f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"


def _deps_snapshot() -> Optional[Dict[str, str]]:
    """Return pip freeze or None if unavailable."""
    try:
        out = subprocess.run(
            [sys.executable, "-m", "pip", "freeze", "--all"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if out.returncode == 0 and out.stdout:
            raw_lines = out.stdout.strip().splitlines()
            lines = [ln.strip() for ln in raw_lines if "==" in ln]
            return {p.split("==")[0]: p.split("==")[1] for p in lines[:50]}
    except Exception:
        pass
    return None


def _expand_ablations(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Expand ablations into Cartesian product of conditions.
    Each condition is a dict with keys from ablations and single values.
    If ablations missing or empty, return [{}].
    """
    ablations = spec.get("ablations") or {}
    if not ablations:
        return [{}]
    keys = sorted(ablations.keys())
    value_lists = [ablations[k] if isinstance(ablations[k], list) else [ablations[k]] for k in keys]
    conditions = []
    for combo in itertools.product(*value_lists):
        conditions.append(dict(zip(keys, combo)))
    return conditions


def _condition_id(index: int) -> str:
    return f"cond_{index}"


def _condition_seed(seed_base: int, condition_index: int) -> int:
    """Deterministic seed for this condition (same spec + index => same seed)."""
    return seed_base + condition_index


def _initial_state_overrides(
    spec: Dict[str, Any],
    condition: Dict[str, Any],
) -> Dict[str, Any]:
    """Build initial_state overrides from spec (timing_mode) and condition."""
    overrides: Dict[str, Any] = {}
    timing = spec.get("timing_mode", "explicit")
    overrides["timing_mode"] = timing
    for k, v in condition.items():
        overrides[f"ablation_{k}"] = v
    return overrides


def _hash_results_for_determinism(results: Dict[str, Any]) -> str:
    """Canonical hash of results dict for determinism checks."""
    payload = json.dumps(results, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def run_study(
    spec_path: Path,
    out_dir: Path,
    repo_root: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Load study spec, expand conditions, run benchmark per condition,
    write artifact dir. Returns summary dict with condition_ids and result_hashes.
    """
    import yaml

    repo_root = repo_root or Path.cwd()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    spec_data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if isinstance(spec_data, dict) and "study_spec" in spec_data:
        spec = spec_data["study_spec"]
    else:
        spec = spec_data if isinstance(spec_data, dict) else {}

    task = spec.get("task", "TaskA")
    episodes = int(spec.get("episodes", 2))
    seed_base = int(spec.get("seed_base", 0))

    conditions = _expand_ablations(spec)
    condition_ids: List[str] = []
    result_hashes: List[str] = []

    (out_dir / "results").mkdir(exist_ok=True)
    (out_dir / "logs").mkdir(exist_ok=True)

    conditions_file = out_dir / "conditions.jsonl"
    with conditions_file.open("w", encoding="utf-8") as f:
        for idx, condition in enumerate(conditions):
            cid = _condition_id(idx)
            condition_ids.append(cid)
            seed = _condition_seed(seed_base, idx)
            overrides = _initial_state_overrides(spec, condition)
            record = {
                "condition_id": cid,
                "condition_index": idx,
                "condition": condition,
                "task": task,
                "episodes": episodes,
                "seed_base": seed_base,
                "condition_seed": seed,
                "initial_state_overrides": overrides,
                "agent_config": spec.get("agent_config", "scripted_runner"),
            }
            f.write(json.dumps(record, sort_keys=True) + "\n")

            results_path = out_dir / "results" / cid / "results.json"
            logs_path = out_dir / "logs" / cid / "episodes.jsonl"
            results_path.parent.mkdir(parents=True, exist_ok=True)
            logs_path.parent.mkdir(parents=True, exist_ok=True)

            run_benchmark(
                task_name=task,
                num_episodes=episodes,
                base_seed=seed,
                out_path=results_path,
                repo_root=repo_root,
                log_path=logs_path,
                initial_state_overrides=overrides,
            )

            results = json.loads(results_path.read_text(encoding="utf-8"))
            result_hashes.append(_hash_results_for_determinism(results))

    git_hash = _git_commit_hash(repo_root)
    policy_versions = _policy_versions(repo_root)
    manifest = {
        "study_spec_path": str(spec_path.resolve()),
        "out_dir": str(out_dir.resolve()),
        "task": task,
        "episodes": episodes,
        "seed_base": seed_base,
        "num_conditions": len(conditions),
        "condition_ids": condition_ids,
        "result_hashes": result_hashes,
        "git_commit_hash": git_hash,
        "policy_versions": policy_versions,
        "python_version": _python_version(),
        "deps_snapshot": _deps_snapshot(),
    }

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return manifest


def main(
    spec_path: Path, out_dir: Path, repo_root: Optional[Path] = None
) -> int:
    """CLI entry: run study and write artifact dir."""
    run_study(spec_path, out_dir, repo_root)
    print(f"Study written to {out_dir}", file=sys.stderr)
    return 0
