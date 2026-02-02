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
                    versions["emits_vocab"] = (
                        line.split("version:")[-1].strip().strip('"')
                    )
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
    calibration = (
        initial_state_overrides.get("calibration") if initial_state_overrides else None
    )
    initial_state = task.get_initial_state(episode_seed, calibration=calibration)
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
    # Optional: external agents (LabTrustAgent protocol) get reset(seed, policy_summary, partner_id, timing_mode)
    policy_summary = initial_state.get("policy_summary")
    partner_id = initial_state.get("partner_id")
    for _aid, agent in scripted_agents_map.items():
        reset_fn = getattr(agent, "reset", None)
        if callable(reset_fn):
            reset_fn(
                episode_seed,
                policy_summary,
                partner_id,
                str(initial_state.get("timing_mode", "explicit")).strip().lower()
                or "explicit",
            )
    step_results_per_step: List[List[Dict[str, Any]]] = []
    t_s_list: List[int] = []
    dt_s = getattr(env, "_dt_s", 10)
    timing_mode = str(initial_state.get("timing_mode", "explicit")).strip().lower()
    if timing_mode not in ("explicit", "simulated"):
        timing_mode = "explicit"
    queue_lengths_per_step: List[Dict[str, int]] = []

    for _ in range(task.max_steps):
        actions: Dict[str, Any] = {}
        action_infos: Dict[str, Dict[str, Any]] = {}
        for agent_id in env.agents:
            if agent_id in scripted_agents_map:
                agent = scripted_agents_map[agent_id]
                ret = agent.act(obs.get(agent_id, {}), agent_id)
                a_idx = ret[0]
                a_info = ret[1] if len(ret) > 1 else {}
                meta = ret[2] if len(ret) > 2 else {}
                actions[agent_id] = a_idx
                if a_info or meta:
                    action_infos[agent_id] = {**(a_info or {}), **(meta or {})}
            else:
                actions[agent_id] = 0
        obs, rewards, term, trunc, infos = env.step(actions, action_infos=action_infos)
        first_agent = list(env.agents)[0] if env.agents else None
        step_results = []
        if first_agent:
            step_results = infos.get(first_agent, {}).get("_benchmark_step_results", [])
        step_results_per_step.append(step_results)
        t_s_list.append(len(step_results_per_step) * dt_s)
        if (
            timing_mode == "simulated"
            and hasattr(env, "_engine")
            and hasattr(env, "_device_ids")
        ):
            q_per_dev: Dict[str, int] = {}
            for dev in getattr(env, "_device_ids", []):
                try:
                    q_per_dev[dev] = int(env._engine.query(f"queue_length('{dev}')"))
                except (ValueError, TypeError):
                    q_per_dev[dev] = 0
            if q_per_dev:
                queue_lengths_per_step.append(q_per_dev)

    timing_summary: Dict[str, Any] = {}
    if hasattr(env, "get_timing_summary"):
        timing_summary = env.get_timing_summary()
    episode_time_s = timing_summary.get("episode_time_s")
    device_busy_s = timing_summary.get("device_busy_s") or {}
    env.close()

    metrics = compute_episode_metrics(
        step_results_per_step,
        t_s_per_step=t_s_list,
        sla_turnaround_s=task.sla_turnaround_s,
        attack_start_step=getattr(task, "attack_start_step", None),
        insider_attack_steps=getattr(task, "insider_attack_steps", None),
        timing_mode=timing_summary.get("timing_mode", timing_mode),
        episode_time_s=episode_time_s,
        device_busy_s=device_busy_s if device_busy_s else None,
        queue_lengths_per_step=(
            queue_lengths_per_step if queue_lengths_per_step else None
        ),
    )
    return metrics, step_results_per_step


def _default_pz_to_engine(
    num_runners: int = 2, num_insiders: int = 0
) -> Dict[str, str]:
    """Standard PZ agent -> engine agent_id mapping (matches LabTrustParallelEnv default)."""
    d: Dict[str, str] = {"ops_0": "A_OPS_0"}
    for i in range(num_runners):
        d[f"runner_{i}"] = f"A_RUNNER_{i}"
    d["qc_0"] = "A_QC_0"
    d["supervisor_0"] = "A_SUPERVISOR_0"
    for i in range(num_insiders):
        d[f"adversary_insider_{i}"] = f"A_INSIDER_{i}"
    return d


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
    partner_id: Optional[str] = None,
    use_llm_safe_v1_ops: bool = False,
    timing_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run N episodes for the task, write results.json.

    Returns the full results dict (also written to out_path).
    log_path: optional JSONL path for episode step log (truncated at start).
    initial_state_overrides: optional dict merged into each episode initial_state (e.g. timing_mode).
    partner_id: optional partner overlay ID; effective_policy and policy_fingerprint injected into initial_state.
    timing_mode: optional "explicit" | "simulated"; overrides task default and initial_state_overrides.
    """
    task = get_task(task_name)
    overrides = dict(initial_state_overrides or {})
    if timing_mode is not None:
        overrides["timing_mode"] = timing_mode
    elif task.timing_mode is not None:
        overrides["timing_mode"] = task.timing_mode
    if repo_root is None:
        from labtrust_gym.config import get_repo_root

        repo_root = get_repo_root()
    repo_root = Path(repo_root)
    effective_policy: Optional[Dict[str, Any]] = None
    policy_fingerprint: Optional[str] = None
    if partner_id:
        from labtrust_gym.policy.loader import load_effective_policy

        try:
            effective_policy, policy_fingerprint, _, _ = load_effective_policy(
                repo_root, partner_id=partner_id
            )
        except Exception as e:
            raise RuntimeError(
                f"Failed to load partner overlay {partner_id!r}: {e}"
            ) from e
    if (
        partner_id
        and effective_policy is not None
        and effective_policy.get("calibration")
    ):
        overrides["calibration"] = effective_policy["calibration"]
    initial_state_overrides = overrides if overrides else None
    if log_path is not None:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text("", encoding="utf-8")
    if env_factory is None:
        from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

        num_adversaries = (
            1 if task_name in ("TaskD", "TaskD_AdversarialDisruption") else 0
        )
        num_insiders = 1 if task_name in ("TaskF", "TaskF_InsiderAndKeyMisuse") else 0
        num_runners = 1 if num_insiders else 2

        policy_dir = repo_root / "policy"

        def _env_factory(
            initial_state: Dict[str, Any],
            reward_config: Dict[str, Any],
            log_path: Optional[Path] = None,
            policy_fingerprint: Optional[str] = None,
            partner_id: Optional[str] = None,
        ) -> Any:
            return LabTrustParallelEnv(
                num_runners=num_runners,
                num_adversaries=num_adversaries,
                num_insiders=num_insiders,
                dt_s=10,
                reward_config=reward_config,
                policy_dir=policy_dir,
                log_path=log_path,
            )

        def _make_env(
            initial_state: Dict[str, Any],
            reward_config: Dict[str, Any],
            log_path: Optional[Path] = None,
        ) -> Any:
            return _env_factory(
                initial_state,
                reward_config,
                log_path,
                policy_fingerprint=policy_fingerprint,
                partner_id=partner_id,
            )

        env_factory = _make_env

    if scripted_agents_map is None:
        from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
        from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
        from labtrust_gym.envs.pz_parallel import (
            DEFAULT_ZONE_IDS,
            DEFAULT_DEVICE_IDS,
        )

        num_insiders = 1 if task_name in ("TaskF", "TaskF_InsiderAndKeyMisuse") else 0
        num_runners = 1 if num_insiders else 2
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
        if use_llm_safe_v1_ops:
            from labtrust_gym.baselines.llm.agent import (
                LLMAgentWithShield,
                DeterministicConstrainedBackend,
            )
            from labtrust_gym.engine.rbac import load_rbac_policy

            rbac_path = (
                (repo_root or Path.cwd()) / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
            )
            rbac_policy = load_rbac_policy(rbac_path)
            pz_to_engine = _default_pz_to_engine(
                num_runners=num_runners, num_insiders=num_insiders
            )
            scripted_agents_map["ops_0"] = LLMAgentWithShield(
                backend=DeterministicConstrainedBackend(
                    seed=base_seed, default_action_type="NOOP"
                ),
                rbac_policy=rbac_policy,
                pz_to_engine=pz_to_engine,
                strict_signatures=False,
            )
        if task_name in ("TaskD", "TaskD_AdversarialDisruption"):
            from labtrust_gym.baselines.adversary import AdversaryAgent

            scripted_agents_map["adversary_0"] = AdversaryAgent()
        if task_name in ("TaskF", "TaskF_InsiderAndKeyMisuse"):
            from labtrust_gym.baselines.insider_adversary import InsiderAdversaryAgent

            scripted_agents_map["adversary_insider_0"] = InsiderAdversaryAgent()

    seeds = [base_seed + i for i in range(num_episodes)]
    episodes_metrics: List[Dict[str, Any]] = []

    use_fresh_agents_per_episode = task_name in ("TaskD", "TaskD_AdversarialDisruption")
    use_fresh_agents_taskf = task_name in ("TaskF", "TaskF_InsiderAndKeyMisuse")

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
        if use_fresh_agents_taskf and scripted_agents_map is not None:
            from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
            from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
            from labtrust_gym.baselines.insider_adversary import InsiderAdversaryAgent
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
                "adversary_insider_0": InsiderAdversaryAgent(),
            }
        metrics, _ = run_episode(
            task,
            ep_seed,
            env_factory,
            agents_map,
            log_path=log_path,
            initial_state_overrides=initial_state_overrides or None,
        )
        episodes_metrics.append({"seed": ep_seed, "metrics": metrics})

    policy_versions = _policy_versions(repo_root)
    git_hash = _git_commit_hash(repo_root)
    partner_id_result = partner_id
    policy_fingerprint_result = policy_fingerprint
    agent_baseline_id = (
        "adversary_v1"
        if task_name in ("TaskD", "TaskD_AdversarialDisruption")
        else (
            "insider_v1"
            if task_name in ("TaskF", "TaskF_InsiderAndKeyMisuse")
            else "scripted_ops_v1"
        )
    )

    effective_timing = (initial_state_overrides or {}).get("timing_mode", "explicit")
    results = {
        "schema_version": "0.2",
        "task": task_name,
        "num_episodes": num_episodes,
        "base_seed": base_seed,
        "seeds": seeds,
        "config": {
            "max_steps": task.max_steps,
            "scripted_agents": task.scripted_agents,
            "reward_config": task.reward_config,
            "timing_mode": effective_timing,
        },
        "policy_versions": policy_versions,
        "git_sha": git_hash,
        "git_commit_hash": git_hash,
        "partner_id": partner_id_result,
        "policy_fingerprint": policy_fingerprint_result,
        "agent_baseline_id": agent_baseline_id,
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
    if repo_root is None:
        from labtrust_gym.config import get_repo_root

        repo_root = get_repo_root()
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
