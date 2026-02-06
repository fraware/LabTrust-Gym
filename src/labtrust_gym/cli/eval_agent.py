"""
eval-agent CLI: run benchmark with an external agent loaded from module:Class or module:function.

Outputs conform to results.v0.2 (and optionally v0.3 if enabled). No network calls; CLI stays fast.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.agent_api import load_agent, wrap_agent_for_runner
from labtrust_gym.benchmarks.runner import run_benchmark
from labtrust_gym.config import get_repo_root


def run_eval_agent(
    task: str,
    episodes: int,
    agent_spec: str,
    out_path: Path,
    *,
    seed: int = 123,
    partner_id: str | None = None,
    timing: str | None = None,
    repo_root: Path | None = None,
    pipeline_mode: str = "deterministic",
    allow_network: bool = False,
) -> dict[str, Any]:
    """
    Load agent from agent_spec (module:Class or module:function), run N episodes, write results.json.

    Returns the results dict (schema v0.2). Agent replaces ops_0; runners remain scripted.
    """
    if repo_root is None:
        repo_root = get_repo_root()
    repo_root = Path(repo_root)
    agent = load_agent(agent_spec, repo_root=repo_root)
    wrapped = wrap_agent_for_runner(agent)
    from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
    from labtrust_gym.envs.pz_parallel import DEFAULT_DEVICE_IDS, DEFAULT_ZONE_IDS

    scripted_agents_map: dict[str, Any] = {
        "ops_0": wrapped,
        "runner_0": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS,
            device_ids=DEFAULT_DEVICE_IDS,
        ),
        "runner_1": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS,
            device_ids=DEFAULT_DEVICE_IDS,
        ),
    }
    if task in ("TaskD", "TaskD_AdversarialDisruption"):
        from labtrust_gym.baselines.adversary import AdversaryAgent

        scripted_agents_map["adversary_0"] = AdversaryAgent()
    if task in ("TaskF", "TaskF_InsiderAndKeyMisuse"):
        from labtrust_gym.baselines.insider_adversary import InsiderAdversaryAgent

        scripted_agents_map["adversary_insider_0"] = InsiderAdversaryAgent()
    # Baseline id for results: sanitized spec (e.g. examples.external_agent_demo:SafeNoOpAgent -> external_plugin)
    agent_baseline_id = _spec_to_baseline_id(agent_spec)
    overrides: dict[str, Any] = {}
    if timing is not None:
        overrides["timing_mode"] = timing
    if partner_id is not None:
        overrides["partner_id"] = partner_id
    results = run_benchmark(
        task_name=task,
        num_episodes=episodes,
        base_seed=seed,
        out_path=out_path,
        repo_root=repo_root,
        scripted_agents_map=scripted_agents_map,
        partner_id=partner_id,
        timing_mode=timing,
        initial_state_overrides=overrides if overrides else None,
        pipeline_mode=pipeline_mode,
        allow_network=allow_network,
    )
    # Override agent_baseline_id so results reflect the external agent
    results["agent_baseline_id"] = agent_baseline_id
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    return results


def _spec_to_baseline_id(spec: str) -> str:
    """Sanitize agent spec to a short baseline id for results (no colons, no dots in class part)."""
    s = (spec or "").strip()
    if ":" in s:
        mod, name = s.split(":", 1)
        return f"{mod}_{name}".replace(".", "_")
    return s.replace(".", "_") or "external_agent"


def register_parser(subparsers: Any) -> None:
    """Register eval-agent subcommand."""
    p = subparsers.add_parser(
        "eval-agent",
        help="Run benchmark with an external agent (module:Class or module:function); write results.json (v0.2).",
    )
    p.add_argument(
        "--task",
        required=True,
        help="Task name: TaskA, TaskB, TaskC, TaskD, TaskE, TaskF",
    )
    p.add_argument(
        "--episodes",
        type=int,
        default=5,
        help="Number of episodes (default 5)",
    )
    p.add_argument(
        "--agent",
        required=True,
        metavar="SPEC",
        help='Agent spec: "module.path:ClassName" or "module.path:function_name"',
    )
    p.add_argument(
        "--out",
        default="results.json",
        help="Output JSON path (default results.json)",
    )
    p.add_argument(
        "--seed",
        type=int,
        default=123,
        help="Base seed (default 123)",
    )
    p.add_argument(
        "--partner",
        default=None,
        help="Partner overlay ID (e.g. hsl_like); also LABTRUST_PARTNER env",
    )
    p.add_argument(
        "--timing",
        choices=["explicit", "simulated"],
        default=None,
        help="Timing mode (default: task default)",
    )
    p.add_argument(
        "--pipeline-mode",
        choices=["deterministic", "llm_offline", "llm_live"],
        default="deterministic",
        help="Pipeline mode (default: deterministic); llm_live requires --allow-network",
    )
    p.add_argument(
        "--allow-network",
        action="store_true",
        help="Allow network for live LLM (only with --pipeline-mode llm_live); also LABTRUST_ALLOW_NETWORK=1",
    )
    p.set_defaults(func=_run_eval_agent)


def _run_eval_agent(args: argparse.Namespace) -> int:
    """CLI entry for eval-agent."""
    import os

    from labtrust_gym.config import get_repo_root

    root = get_repo_root()
    out = Path(args.out)
    if not out.is_absolute():
        out = root / out
    pipeline_mode = getattr(args, "pipeline_mode", "deterministic") or "deterministic"
    allow_network = getattr(args, "allow_network", False) or (
        (os.environ.get("LABTRUST_ALLOW_NETWORK") or "").strip().lower()
        in ("1", "true", "yes")
    )
    run_eval_agent(
        task=args.task,
        episodes=args.episodes,
        agent_spec=args.agent,
        out_path=out,
        seed=args.seed,
        partner_id=getattr(args, "partner", None),
        timing=getattr(args, "timing", None),
        repo_root=root,
        pipeline_mode=pipeline_mode,
        allow_network=allow_network,
    )
    print(f"Wrote {out}", file=__import__("sys").stderr)
    return 0
