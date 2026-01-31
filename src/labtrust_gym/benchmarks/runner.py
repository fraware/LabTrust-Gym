"""
Benchmark runner: run N episodes for a task, record metrics, output JSON.

Writes results.json with metadata: git commit, policy versions, seeds, config.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from labtrust_gym.benchmarks.metrics import compute_episode_metrics
from labtrust_gym.benchmarks.tasks import BenchmarkTask, get_task


def _git_commit_hash(cwd: Optional[Path] = None) -> Optional[str]:
    """Return current git commit hash or None."""
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
    """Read policy file versions (emits vocab, catalogue schema, etc.)."""
    versions: Dict[str, str] = {}
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if emits_path.exists():
        try:
            data = emits_path.read_text(encoding="utf-8")
            for line in data.splitlines()[:20]:
                if "version:" in line:
                    versions["emits_vocab"] = line.split("version:")[-1].strip().strip('"')
                    break
        except Exception:
            versions["emits_vocab"] = "unknown"
    catalogue_path = root / "policy" / "schemas" / "test_catalogue.schema.v0.1.json"
    if catalogue_path.exists():
        try:
            data = json.loads(catalogue_path.read_text(encoding="utf-8"))
            versions["catalogue_schema"] = data.get("schema_version", "unknown")
        except Exception:
            versions["catalogue_schema"] = "unknown"
    return versions


def run_episode(
    task: BenchmarkTask,
    episode_seed: int,
    env_factory: Any,
    scripted_agents_map: Optional[Dict[str, Any]] = None,
    log_path: Optional[Path] = None,
    initial_state_overrides: Optional[Dict[str, Any]] = None,
) -> tuple[Dict[str, Any], List[List[Dict[str, Any]]]]:
    """
    Run one episode. Returns (metrics_dict, step_results_per_step).

    env_factory: callable(initial_state, reward_config, log_path=?) -> env.
    scripted_agents_map: agent_id -> agent with .act(obs, agent_id) -> (idx, info).
    log_path: optional JSONL path for episode step log (append mode).
    initial_state_overrides: optional dict merged into initial_state (e.g. timing_mode, ablations).
    """
    initial_state = task.get_initial_state(episode_seed)
    if initial_state_overrides:
        initial_state = {**initial_state, **initial_state_overrides}
    env = env_factory(
        initial_state=initial_state,
        reward_config=task.reward_config,
        log_path=log_path,
    )
    obs, _ = env.reset(
        seed=episode_seed,
        options={"initial_state": initial_state},
    )
    scripted_agents_map = scripted_agents_map or {}
    step_results_per_step: List[List[Dict[str, Any]]] = []
    t_s_list: List[int] = []
    dt_s = getattr(env, "_dt_s", 10)

    for _ in range(task.max_steps):
        actions: Dict[str, Any] = {}
        action_infos: Dict[str, Dict[str, Any]] = {}
        for agent_id in env.agents:
            if agent_id in scripted_agents_map:
                agent = scripted_agents_map[agent_id]
                a_idx, a_info = agent.act(obs.get(agent_id, {}), agent_id)
                actions[agent_id] = a_idx
                if a_info and a_idx not in (0, 1):
                    action_infos[agent_id] = a_info
            else:
                actions[agent_id] = 0
        obs, rewards, term, trunc, infos = env.step(
            actions, action_infos=action_infos
        )
        first_agent = list(env.agents)[0] if env.agents else None
        step_results = []
        if first_agent:
            step_results = infos.get(first_agent, {}).get(
                "_benchmark_step_results", []
            )
        step_results_per_step.append(step_results)
        t_s_list.append(len(step_results_per_step) * dt_s)

    env.close()

    metrics = compute_episode_metrics(
        step_results_per_step,
        t_s_per_step=t_s_list,
        sla_turnaround_s=task.sla_turnaround_s,
        attack_start_step=getattr(task, "attack_start_step", None),
    )
    return metrics, step_results_per_step


def run_benchmark(
    task_name: str,
    num_episodes: int,
    base_seed: int,
    out_path: Path,
    env_factory: Optional[Any] = None,
    scripted_agents_map: Optional[Dict[str, Any]] = None,
    repo_root: Optional[Path] = None,
    log_path: Optional[Path] = None,
    initial_state_overrides: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Run N episodes for the task, write results.json.

    Returns the full results dict (also written to out_path).
    log_path: optional JSONL path for episode step log (truncated at start).
    initial_state_overrides: optional dict merged into each episode initial_state (e.g. timing_mode).
    """
    task = get_task(task_name)
    repo_root = repo_root or Path.cwd()
    if log_path is not None:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text("", encoding="utf-8")
    if env_factory is None:
        from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

        num_adversaries = 1 if task_name in ("TaskD", "TaskD_AdversarialDisruption") else 0

        def _env_factory(
            initial_state: Dict[str, Any],
            reward_config: Dict[str, Any],
            log_path: Optional[Path] = None,
        ) -> Any:
            return LabTrustParallelEnv(
                num_runners=2,
                num_adversaries=num_adversaries,
                dt_s=10,
                reward_config=reward_config,
                log_path=log_path,
            )

        env_factory = _env_factory

    if scripted_agents_map is None:
        from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
        from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
        from labtrust_gym.envs.pz_parallel import (
            DEFAULT_ZONE_IDS,
            DEFAULT_DEVICE_IDS,
        )
        scripted_agents_map = {
            "ops_0": ScriptedOpsAgent(),
            "runner_0": ScriptedRunnerAgent(
                zone_ids=DEFAULT_ZONE_IDS,
                device_ids=DEFAULT_DEVICE_IDS,
            ),
            "runner_1": ScriptedRunnerAgent(
                zone_ids=DEFAULT_ZONE_IDS,
                device_ids=DEFAULT_DEVICE_IDS,
            ),
        }
        if task_name in ("TaskD", "TaskD_AdversarialDisruption"):
            from labtrust_gym.baselines.adversary import AdversaryAgent
            scripted_agents_map["adversary_0"] = AdversaryAgent()

    seeds = [base_seed + i for i in range(num_episodes)]
    episodes_metrics: List[Dict[str, Any]] = []

    use_fresh_agents_per_episode = task_name in ("TaskD", "TaskD_AdversarialDisruption")

    for ep_seed in seeds:
        agents_map = scripted_agents_map
        if use_fresh_agents_per_episode and scripted_agents_map is not None:
            from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
            from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
            from labtrust_gym.baselines.adversary import AdversaryAgent
            from labtrust_gym.envs.pz_parallel import (
                DEFAULT_ZONE_IDS,
                DEFAULT_DEVICE_IDS,
            )
            agents_map = {
                "ops_0": ScriptedOpsAgent(),
                "runner_0": ScriptedRunnerAgent(
                    zone_ids=DEFAULT_ZONE_IDS,
                    device_ids=DEFAULT_DEVICE_IDS,
                ),
                "runner_1": ScriptedRunnerAgent(
                    zone_ids=DEFAULT_ZONE_IDS,
                    device_ids=DEFAULT_DEVICE_IDS,
                ),
                "adversary_0": AdversaryAgent(),
            }
        metrics, _ = run_episode(
            task,
            ep_seed,
            env_factory,
            agents_map,
            log_path=log_path,
            initial_state_overrides=initial_state_overrides,
        )
        episodes_metrics.append({"seed": ep_seed, "metrics": metrics})

    policy_versions = _policy_versions(repo_root)
    git_hash = _git_commit_hash(repo_root)

    results = {
        "task": task_name,
        "num_episodes": num_episodes,
        "base_seed": base_seed,
        "seeds": seeds,
        "config": {
            "max_steps": task.max_steps,
            "scripted_agents": task.scripted_agents,
            "reward_config": task.reward_config,
        },
        "policy_versions": policy_versions,
        "git_commit_hash": git_hash,
        "episodes": episodes_metrics,
    }

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    return results


def main(
    task: str,
    episodes: int,
    seed: int,
    out: str,
    repo_root: Optional[Path] = None,
    log_path: Optional[str] = None,
) -> int:
    """CLI entry: run benchmark and write results.json."""
    repo_root = repo_root or _find_repo_root()
    run_benchmark(
        task_name=task,
        num_episodes=episodes,
        base_seed=seed,
        out_path=Path(out),
        repo_root=repo_root,
        log_path=Path(log_path) if log_path else None,
    )
    print(f"Wrote {out}", file=sys.stderr)
    return 0


def _find_repo_root() -> Path:
    cwd = Path.cwd()
    for p in [cwd, cwd.parent]:
        if (p / "policy").is_dir():
            return p
    return cwd
