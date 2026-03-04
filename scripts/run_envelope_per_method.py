"""
Run a short coordination-method probe and write envelope_<method_id>.yaml (step_ms, optional LLM latency).

For each method_id in the list, runs propose_actions for a fixed number of steps with minimal obs,
records wall-clock per step, and writes docs/benchmarks/envelopes/envelope_<method_id>.yaml (or
--out-dir if set). Used for SOTA envelope documentation (max agents, typical step_ms, recommended hardware).

Usage (from repo root):
  python scripts/run_envelope_per_method.py [--methods kernel_whca llm_central_planner] [--steps 20] [--out-dir docs/benchmarks/envelopes]
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _minimal_policy(repo: Path) -> dict:
    from labtrust_gym.policy.loader import load_yaml

    zone_path = repo / "policy" / "zones" / "zone_layout_policy.v0.1.yaml"
    if zone_path.exists():
        data = load_yaml(zone_path)
        layout = data.get("zone_layout") or data
    else:
        layout = {"zones": [], "graph_edges": [], "device_placement": []}
    return {
        "zone_layout": layout,
        "pz_to_engine": {"worker_0": "ops_0", "worker_1": "runner_0", "worker_2": "runner_1"},
    }


def _minimal_obs(agent_ids: list[str], t: int) -> dict:
    obs = {}
    for i, aid in enumerate(agent_ids):
        obs[aid] = {
            "my_zone_idx": 1 + (i + t) % 2,
            "zone_id": "Z_SORTING_LANES" if i == 0 else "Z_ANALYZER_HALL_A",
            "queue_has_head": [0] * 2,
            "queue_by_device": [{"queue_head": "", "queue_len": 0}, {"queue_head": "", "queue_len": 0}],
            "log_frozen": 0,
        }
    return obs


def run_envelope(
    method_id: str,
    repo_root: Path,
    steps: int = 20,
) -> dict:
    """Run propose_actions `steps` times, return dict with step_ms_mean, step_ms_p95, etc."""
    from labtrust_gym.baselines.coordination.registry import make_coordination_method

    policy = _minimal_policy(repo_root)
    scale_config = {"num_agents_total": 3, "horizon_steps": 10, "seed": 42}
    try:
        method = make_coordination_method(
            method_id,
            policy,
            repo_root=repo_root,
            scale_config=scale_config,
        )
    except Exception as e:
        return {"error": str(e), "method_id": method_id}
    method.reset(42, policy, scale_config)
    agent_ids = sorted(policy.get("pz_to_engine", {}))
    latencies_ms: list[float] = []
    for t in range(steps):
        obs = _minimal_obs(agent_ids, t)
        start = time.perf_counter()
        method.propose_actions(obs, {}, t)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies_ms.append(elapsed_ms)
    if not latencies_ms:
        return {"method_id": method_id, "step_ms_mean": 0.0, "step_ms_p95": 0.0}
    latencies_ms.sort()
    n = len(latencies_ms)
    mean_ms = sum(latencies_ms) / n
    p95_ms = latencies_ms[int(n * 0.95)] if n > 1 else latencies_ms[0]
    return {
        "method_id": method_id,
        "scale_id": "small_smoke",
        "step_ms_mean": round(mean_ms, 2),
        "step_ms_p95": round(p95_ms, 2),
        "steps": steps,
        "max_agents": 3,
        "max_devices": 2,
        "recommended_hardware": "CI/single-core probe",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Run envelope probe per coordination method")
    ap.add_argument(
        "--methods",
        nargs="+",
        default=["kernel_whca", "llm_central_planner", "centralized_planner"],
        help="Method IDs to probe",
    )
    ap.add_argument("--steps", type=int, default=20, help="Steps per method")
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Output directory for envelope YAMLs (default: docs/benchmarks/envelopes)",
    )
    args = ap.parse_args()
    repo = _repo_root()
    out_dir = args.out_dir or repo / "docs" / "benchmarks" / "envelopes"
    out_dir.mkdir(parents=True, exist_ok=True)
    for method_id in args.methods:
        result = run_envelope(method_id, repo, steps=args.steps)
        if "error" in result:
            print(f"{method_id}: skip ({result['error']})")
            continue
        out_path = out_dir / f"envelope_{method_id}.yaml"
        import yaml

        with out_path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(result, f, default_flow_style=False, sort_keys=False)
        print(f"{method_id}: step_ms_mean={result['step_ms_mean']} -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
