"""
Benchmark runner: run N episodes for a task, record metrics, output JSON.

Writes results.json with metadata: git commit, policy versions, seeds, config.
When coordination is used, writes coord_decisions.jsonl (contract v0.1) per episode.
"""

from __future__ import annotations

import json
import os
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
    coord_method: Optional[Any] = None,
    risk_injector: Optional[Any] = None,
    comms_config: Optional[Any] = None,
) -> tuple[Dict[str, Any], List[List[Dict[str, Any]]]]:
    """
    Run one episode. Returns (metrics_dict, step_results_per_step).

    env_factory: callable(initial_state, reward_config, log_path=?) -> env.
    scripted_agents_map: agent_id -> agent with .act(obs, agent_id) -> (idx, info).
    log_path: optional JSONL path for episode step log (append mode).
    initial_state_overrides: optional dict merged into initial_state (e.g. timing_mode, ablations).
    coord_method: optional CoordinationMethod; when set, propose_actions drives all agents (TaskG/TaskH).
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
    policy_summary = initial_state.get("policy_summary")
    partner_id = initial_state.get("partner_id")
    effective_policy = initial_state.get("effective_policy") or policy_summary or {}
    scale_config_dict: Dict[str, Any] = {}
    if hasattr(task, "scale_config") and task.scale_config is not None:
        from dataclasses import asdict

        scale_config_dict = asdict(task.scale_config)
    if initial_state.get("injection_id"):
        scale_config_dict = dict(scale_config_dict)
        scale_config_dict["injection_id"] = initial_state["injection_id"]
    if risk_injector is not None:
        risk_injector.reset(episode_seed, None)
    if coord_method is not None:
        coord_method.reset(episode_seed, effective_policy, scale_config_dict)
    else:
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
    coord_decisions_path: Optional[Path] = None
    if coord_method is not None and log_path is not None:
        coord_decisions_path = log_path.parent / "coord_decisions.jsonl"
        coord_decisions_path.write_text("", encoding="utf-8")
    timing_mode = str(initial_state.get("timing_mode", "explicit")).strip().lower()
    if timing_mode not in ("explicit", "simulated"):
        timing_mode = "explicit"
    queue_lengths_per_step: List[Dict[str, int]] = []
    infos: Dict[str, Dict[str, Any]] = {}
    total_critical_episode = 0
    stale_count_episode = 0
    view_ages_ms_episode: List[float] = []
    dt_ms = 10000.0

    blackboard_harness: Optional[Any] = None
    if coord_method is not None and (getattr(task, "scale_config", None) is not None):
        from labtrust_gym.coordination.harness import BlackboardHarness
        from labtrust_gym.coordination.comms_model import CommsConfig

        agent_ids = list(env.agents)
        device_ids = list(getattr(env, "_device_ids", []) or [])
        zone_ids = list(getattr(env, "_zone_ids", []) or [])
        cfg = comms_config if comms_config is not None else CommsConfig(perfect=True)
        blackboard_harness = BlackboardHarness(
            agent_ids=agent_ids,
            device_ids=device_ids,
            zone_ids=zone_ids,
            comms_config=cfg,
            seed=episode_seed,
        )
        clock_skew_config = None
        if risk_injector is not None and hasattr(risk_injector, "get_clock_config"):
            clock_skew_config = risk_injector.get_clock_config(agent_ids)
        blackboard_harness.reset(
            episode_seed,
            clock_skew_config=clock_skew_config,
        )
        dt_ms = float(getattr(env, "_dt_s", 10)) * 1000.0

    for step_t in range(task.max_steps):
        view_ages_ms_step = []
        obs_for_step = obs
        audit_obs: Optional[Dict[str, Any]] = None
        if risk_injector is not None:
            obs_for_step, audit_obs = risk_injector.mutate_obs(obs)
        actions: Dict[str, Any] = {}
        action_infos: Dict[str, Dict[str, Any]] = {}
        coord_decision = None
        if coord_method is not None:
            from labtrust_gym.baselines.coordination.interface import (
                action_dict_to_index_and_info,
            )

            if hasattr(coord_method, "step"):
                from labtrust_gym.baselines.coordination.compose import (
                    build_kernel_context,
                )

                context = build_kernel_context(
                    obs_for_step,
                    infos,
                    step_t,
                    effective_policy,
                    scale_config_dict,
                    episode_seed,
                    blackboard_harness=blackboard_harness,
                )
                actions_dict, coord_decision = coord_method.step(context)
            else:
                actions_dict = coord_method.propose_actions(obs_for_step, infos, step_t)
            if risk_injector is not None:
                actions_dict, audit_actions = risk_injector.mutate_actions(actions_dict)
            else:
                audit_actions = []
            for agent_id in env.agents:
                ad = actions_dict.get(agent_id, {"action_index": 0})
                idx, info = action_dict_to_index_and_info(ad)
                actions[agent_id] = idx
                if info:
                    action_infos[agent_id] = dict(info)
            # Coordination timing: detect stale decisions (critical actions on old view)
            stale_emit_payloads_this_step: List[Dict[str, Any]] = []
            if blackboard_harness is not None:
                from labtrust_gym.coordination.coordination_monitor import (
                    check_staleness,
                    count_critical_actions,
                    DEFAULT_MAX_STALENESS_MS,
                )

                view_snapshots = blackboard_harness.view_snapshots()
                stale_count_step, stale_emit_payloads_this_step, view_ages_ms_step = (
                    check_staleness(
                        actions_dict,
                        view_snapshots,
                        step_t,
                        dt_ms=dt_ms,
                        max_staleness_ms=DEFAULT_MAX_STALENESS_MS,
                    )
                )
                total_critical_episode += count_critical_actions(actions_dict)
                stale_count_episode += stale_count_step
                view_ages_ms_episode.extend(view_ages_ms_step)
        else:
            actions_dict = {}
            stale_emit_payloads_this_step = []
            for agent_id in env.agents:
                if agent_id in scripted_agents_map:
                    agent = scripted_agents_map[agent_id]
                    ret = agent.act(obs_for_step.get(agent_id, {}), agent_id)
                    actions_dict[agent_id] = {
                        "action_index": ret[0],
                        **(ret[1] if len(ret) > 1 else {}),
                    }
                else:
                    actions_dict[agent_id] = {"action_index": 0}
            if risk_injector is not None:
                actions_dict, audit_actions = risk_injector.mutate_actions(actions_dict)
            else:
                audit_actions = []
            for agent_id in env.agents:
                ad = actions_dict.get(agent_id, {"action_index": 0})
                actions[agent_id] = ad.get("action_index", 0)
                action_infos[agent_id] = {
                    k: v for k, v in ad.items() if k != "action_index" and v is not None
                }
        obs, rewards, term, trunc, infos = env.step(actions, action_infos=action_infos)
        first_agent = list(env.agents)[0] if env.agents else None
        step_results = list(
            infos.get(first_agent, {}).get("_benchmark_step_results", [])
            if first_agent
            else []
        )
        if risk_injector is not None:
            step_results.extend(audit_actions)
            if audit_obs is not None:
                step_results.append(audit_obs)
            extra = risk_injector.observe_step(step_results)
            step_results.extend(extra)
        if coord_decision is not None:
            step_results.append(
                {
                    "emits": ["COORD_DECISION"],
                    "coord_decision_payload": coord_decision.to_emit_payload(),
                }
            )
        if coord_method is not None:
            shield_emits = getattr(coord_method, "last_shield_emits", None)
            if shield_emits:
                step_results.extend(shield_emits)
        for payload in stale_emit_payloads_this_step:
            step_results.append(
                {
                    "emits": [payload.get("emit", "COORD_STALE_DECISION")],
                    "coord_stale_payload": payload,
                }
            )
        if coord_method is not None and coord_decisions_path is not None:
            from labtrust_gym.baselines.coordination.telemetry import (
                build_contract_record,
                serialize_contract_record,
                validate_contract_record,
            )
            view_age_ms = max(view_ages_ms_step) if view_ages_ms_step else None
            view_age_ms_per_agent = None
            if stale_emit_payloads_this_step:
                view_age_ms_per_agent = {
                    p["agent_id"]: p["view_age_ms"]
                    for p in stale_emit_payloads_this_step
                    if "agent_id" in p and "view_age_ms" in p
                }
            shield_emits = getattr(coord_method, "last_shield_emits", None) or []
            contract_record = build_contract_record(
                method_id=coord_method.method_id,
                t_step=step_t,
                actions_dict=actions_dict,
                view_age_ms=view_age_ms,
                view_age_ms_per_agent=view_age_ms_per_agent,
                plan_time_ms=None,
                invariants_considered=[],
                safety_shield_applied=bool(shield_emits),
                safety_shield_details=(
                    {"count": len(shield_emits)} if shield_emits else None
                ),
            )
            if os.environ.get("LABTRUST_STRICT_COORD_CONTRACT") == "1":
                errs = validate_contract_record(contract_record)
                if errs:
                    raise ValueError(
                        f"Coord contract validation failed at step {step_t}: {errs}"
                    )
            with coord_decisions_path.open("a", encoding="utf-8") as f:
                f.write(serialize_contract_record(contract_record))
        step_results_per_step.append(step_results)
        if coord_method is not None and hasattr(coord_method, "on_step_result"):
            coord_method.on_step_result(step_results)
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

    injection_metrics = None
    injection_id = None
    if risk_injector is not None:
        injection_metrics = risk_injector.get_metrics()
        injection_id = risk_injector.injection_id
    if blackboard_harness is not None:
        comm_metrics = blackboard_harness.get_comm_metrics()
    else:
        comm_metrics = None
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
        injection_metrics=injection_metrics,
        injection_id=injection_id,
    )
    if comm_metrics is not None:
        metrics["coordination"] = {"comm": comm_metrics}
    if blackboard_harness is not None:
        from labtrust_gym.coordination.coordination_monitor import timing_metrics

        timing = timing_metrics(
            total_critical_episode,
            stale_count_episode,
            view_ages_ms_episode,
        )
        metrics.setdefault("coordination", {})["timing"] = timing
    if coord_method is not None:
        route_metrics = getattr(coord_method, "get_route_metrics", lambda: None)()
        if route_metrics is not None:
            metrics.setdefault("coordination", {})["route"] = route_metrics
        alloc_metrics = getattr(coord_method, "get_alloc_metrics", lambda: None)()
        if alloc_metrics is not None:
            metrics.setdefault("coordination", {})["alloc"] = alloc_metrics
        sched_metrics = getattr(
            coord_method, "get_schedule_metrics", lambda: None
        )()
        if sched_metrics is not None:
            metrics.setdefault("coordination", {})["sched"] = sched_metrics
        hierarchy_metrics = getattr(
            coord_method, "get_hierarchy_metrics", lambda: None
        )()
        if hierarchy_metrics is not None:
            metrics.setdefault("coordination", {})["hierarchy"] = hierarchy_metrics
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
    use_llm_live_openai: bool = False,
    llm_backend: Optional[str] = None,
    llm_agents: Optional[List[str]] = None,
    timing_mode: Optional[str] = None,
    coord_method: Optional[str] = None,
    injection_id: Optional[str] = None,
    scale_config_override: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Run N episodes for the task, write results.json.

    Returns the full results dict (also written to out_path).
    log_path: optional JSONL path for episode step log (truncated at start).
    initial_state_overrides: optional dict merged into each episode initial_state (e.g. timing_mode).
    partner_id: optional partner overlay ID; effective_policy and policy_fingerprint injected into initial_state.
    llm_backend: optional "deterministic" | "openai_live" | "ollama_live" to use LLM for agents in llm_agents; None = scripted.
    llm_agents: agent IDs that use LLM (e.g. ["ops_0"] or ["ops_0", "runner_0"]). Default ["ops_0"] when llm_backend set.
    timing_mode: optional "explicit" | "simulated"; overrides task default and initial_state_overrides.
    coord_method: optional coordination method_id for TaskG_COORD_SCALE / TaskH_COORD_RISK (e.g. centralized_planner).
    injection_id: optional risk injection id for TaskH_COORD_RISK (e.g. INJ-ID-SPOOF-001); loads config from study spec.
    scale_config_override: optional CoordinationScaleConfig for TaskG/TaskH; when set, overrides task scale and horizon.
    """
    if llm_backend is None and use_llm_live_openai:
        llm_backend = "openai_live"
    if llm_backend is None and use_llm_safe_v1_ops:
        llm_backend = "deterministic"
    if llm_agents is None and llm_backend is not None:
        llm_agents = ["ops_0"]
    llm_agents = llm_agents or []
    llm_backend_ref: Optional[Any] = None
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
    use_strict_signatures = bool(
        task.get_initial_state(0).get("strict_signatures")
        or (overrides or {}).get("strict_signatures")
    )
    # Inject tool registry so engine can gate tool_id calls (B010).
    try:
        from labtrust_gym.tools.registry import (
            load_tool_registry,
            tool_registry_fingerprint as tool_reg_fp,
        )

        tool_reg = load_tool_registry(repo_root)
        if tool_reg:
            overrides = overrides or {}
            overrides["tool_registry"] = tool_reg
            overrides["tool_registry_fingerprint"] = tool_reg_fp(tool_reg)
            overrides["policy_root"] = repo_root
            try:
                from labtrust_gym.tools.capabilities import (
                    load_state_tool_capability_map,
                )

                state_map = load_state_tool_capability_map(repo_root)
                if state_map:
                    overrides["state_tool_capability_map"] = state_map
            except Exception:
                pass
            try:
                from labtrust_gym.engine.rbac import load_rbac_policy
                from labtrust_gym.auth.authorize import rbac_policy_fingerprint

                rbac_path = repo_root / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
                rbac_policy = load_rbac_policy(rbac_path)
                if rbac_policy and rbac_policy.get("roles"):
                    overrides["rbac_policy_fingerprint"] = rbac_policy_fingerprint(
                        rbac_policy
                    )
            except Exception:
                pass
    except Exception:
        pass
    key_registry_merged: Optional[Dict[str, Any]] = None
    get_private_key_fn: Optional[Any] = None
    if llm_backend and use_strict_signatures:
        from labtrust_gym.baselines.llm.signing_proxy import (
            ensure_run_ephemeral_key,
        )
        from labtrust_gym.engine.signatures import load_key_registry

        key_path = repo_root / "policy" / "keys" / "key_registry.v0.1.yaml"
        key_registry_base = (
            load_key_registry(key_path)
            if key_path.exists()
            else {"version": "0.1", "keys": []}
        )
        run_dir = (log_path or out_path).parent
        key_registry_merged, get_private_key_fn = ensure_run_ephemeral_key(
            run_dir,
            "A_OPS_0",
            "ROLE_ANALYTICS",
            key_registry_base,
        )
        overrides = overrides or {}
        eff = overrides.get("effective_policy") or {}
        overrides["effective_policy"] = {**eff, "key_registry": key_registry_merged}
    initial_state_overrides = overrides if overrides else None
    if log_path is not None:
        Path(log_path).parent.mkdir(parents=True, exist_ok=True)
        Path(log_path).write_text("", encoding="utf-8")
    is_scale_task = task_name in ("TaskG_COORD_SCALE", "TaskH_COORD_RISK")
    scale_probe_state: Optional[Dict[str, Any]] = None
    coord_method_instance: Optional[Any] = None
    if is_scale_task:
        if scale_config_override is not None:
            from labtrust_gym.benchmarks.coordination_scale import (
                generate_scaled_initial_state,
            )

            scale_probe_state = generate_scaled_initial_state(
                scale_config_override, repo_root, base_seed
            )
            task.max_steps = scale_config_override.horizon_steps
        else:
            scale_probe_state = task.get_initial_state(base_seed)
    if is_scale_task and coord_method:
        from dataclasses import asdict
        from labtrust_gym.baselines.coordination.registry import (
            make_coordination_method,
        )

        scale_config_dict = (
            asdict(scale_config_override)
            if scale_config_override is not None
            else (
                asdict(task.scale_config) if getattr(task, "scale_config", None) else {}
            )
        )
        if task_name == "TaskH_COORD_RISK" and injection_id:
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict["injection_id"] = injection_id
        policy_for_coord = (scale_probe_state or {}).get("effective_policy") or {}
        if coord_method == "llm_constrained":
            from labtrust_gym.baselines.llm.agent import (
                DeterministicConstrainedBackend,
                LLMAgentWithShield,
            )
            from labtrust_gym.engine.rbac import load_rbac_policy
            from labtrust_gym.security.agent_capabilities import load_agent_capabilities

            scale_agents = (scale_probe_state or {}).get("agents") or []
            pz_to_engine_scale = {
                f"worker_{i}": scale_agents[i]["agent_id"]
                for i in range(len(scale_agents))
                if i < len(scale_agents)
            }
            rbac_path = repo_root / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
            rbac_policy = load_rbac_policy(rbac_path)
            capability_policy = load_agent_capabilities(repo_root)
            llm_agent = LLMAgentWithShield(
                backend=DeterministicConstrainedBackend(
                    seed=base_seed, default_action_type="NOOP"
                ),
                rbac_policy=rbac_policy,
                pz_to_engine=pz_to_engine_scale,
                strict_signatures=use_strict_signatures,
                key_registry=key_registry_merged or {},
                get_private_key=get_private_key_fn or (lambda _: None),
                capability_policy=capability_policy,
            )
            coord_method_instance = make_coordination_method(
                coord_method,
                policy_for_coord,
                repo_root=repo_root,
                scale_config=scale_config_dict,
                llm_agent=llm_agent,
                pz_to_engine=pz_to_engine_scale,
            )
        else:
            coord_method_instance = make_coordination_method(
                coord_method,
                policy_for_coord,
                repo_root=repo_root,
                scale_config=scale_config_dict,
            )

    if task_name == "TaskH_COORD_RISK" and injection_id == "INJ-ID-SPOOF-001":
        overrides["strict_signatures"] = True
    risk_injector_instance: Optional[Any] = None
    if task_name == "TaskH_COORD_RISK" and injection_id:
        if injection_id == "INJ-BID-SPOOF-001":
            pass
        else:
            from labtrust_gym.policy.coordination import load_coordination_study_spec
            from labtrust_gym.security.risk_injections import make_injector

            spec_path = (
                repo_root
                / "policy"
                / "coordination"
                / "coordination_study_spec.v0.1.yaml"
            )
            intensity = 0.2
            seed_offset = 0
            if spec_path.exists():
                try:
                    spec = load_coordination_study_spec(spec_path)
                    for inj in spec.get("injections") or []:
                        if (
                            isinstance(inj, dict)
                            and inj.get("injection_id") == injection_id
                        ):
                            intensity = float(inj.get("intensity", 0.2))
                            seed_offset = int(inj.get("seed_offset", 0))
                            break
                except Exception:
                    pass
            risk_injector_instance = make_injector(
                injection_id, intensity=intensity, seed_offset=seed_offset
            )

    if env_factory is None:
        from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

        num_adversaries = (
            1 if task_name in ("TaskD", "TaskD_AdversarialDisruption") else 0
        )
        num_insiders = 1 if task_name in ("TaskF", "TaskF_InsiderAndKeyMisuse") else 0
        num_runners = 1 if num_insiders else 2

        policy_dir = repo_root / "policy"

        if is_scale_task and scale_probe_state:
            scale_agents = scale_probe_state.get("agents") or []
            scale_device_ids = scale_probe_state.get("_scale_device_ids")
            scale_zone_ids = scale_probe_state.get("_scale_zone_ids")

            def _env_factory(
                initial_state: Dict[str, Any],
                reward_config: Dict[str, Any],
                log_path: Optional[Path] = None,
                policy_fingerprint: Optional[str] = None,
                partner_id: Optional[str] = None,
            ) -> Any:
                return LabTrustParallelEnv(
                    num_runners=0,
                    num_adversaries=0,
                    num_insiders=0,
                    dt_s=10,
                    reward_config=reward_config,
                    policy_dir=policy_dir,
                    log_path=log_path,
                    scale_agents=scale_agents,
                    scale_device_ids=scale_device_ids,
                    scale_zone_ids=scale_zone_ids,
                )

        else:

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

        if is_scale_task and scale_probe_state:
            scale_agents = scale_probe_state.get("agents") or []
            scale_device_ids = (
                scale_probe_state.get("_scale_device_ids") or DEFAULT_DEVICE_IDS
            )
            scale_zone_ids = (
                scale_probe_state.get("_scale_zone_ids") or DEFAULT_ZONE_IDS
            )
            scripted_agents_map = {
                f"worker_{i}": ScriptedRunnerAgent(
                    zone_ids=scale_zone_ids,
                    device_ids=scale_device_ids,
                )
                for i in range(len(scale_agents))
            }
        else:
            num_insiders = (
                1 if task_name in ("TaskF", "TaskF_InsiderAndKeyMisuse") else 0
            )
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
        if not is_scale_task and llm_backend == "deterministic":
            from labtrust_gym.baselines.llm.agent import (
                LLMAgentWithShield,
                DeterministicConstrainedBackend,
            )
            from labtrust_gym.engine.rbac import load_rbac_policy
            from labtrust_gym.security.agent_capabilities import load_agent_capabilities

            rbac_path = (
                (repo_root or Path.cwd()) / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
            )
            rbac_policy = load_rbac_policy(rbac_path)
            capability_policy = load_agent_capabilities(repo_root or Path.cwd())
            pz_to_engine = _default_pz_to_engine(
                num_runners=num_runners, num_insiders=num_insiders
            )
            for aid in llm_agents:
                if aid not in scripted_agents_map:
                    continue
                scripted_agents_map[aid] = LLMAgentWithShield(
                    backend=DeterministicConstrainedBackend(
                        seed=base_seed, default_action_type="NOOP"
                    ),
                    rbac_policy=rbac_policy,
                    pz_to_engine=pz_to_engine,
                    strict_signatures=use_strict_signatures,
                    key_registry=key_registry_merged,
                    get_private_key=get_private_key_fn,
                    capability_policy=capability_policy,
                )
        elif not is_scale_task and llm_backend == "openai_live":
            from labtrust_gym.baselines.llm.agent import LLMAgentWithShield
            from labtrust_gym.baselines.llm.backends.openai_live import (
                OpenAILiveBackend,
            )
            from labtrust_gym.engine.rbac import load_rbac_policy
            from labtrust_gym.security.agent_capabilities import load_agent_capabilities

            rbac_path = (
                (repo_root or Path.cwd()) / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
            )
            rbac_policy = load_rbac_policy(rbac_path)
            capability_policy = load_agent_capabilities(repo_root or Path.cwd())
            pz_to_engine = _default_pz_to_engine(
                num_runners=num_runners, num_insiders=num_insiders
            )
            backend = OpenAILiveBackend()
            llm_backend_ref = backend
            for aid in llm_agents:
                if aid not in scripted_agents_map:
                    continue
                scripted_agents_map[aid] = LLMAgentWithShield(
                    backend=backend,
                    rbac_policy=rbac_policy,
                    pz_to_engine=pz_to_engine,
                    strict_signatures=use_strict_signatures,
                    key_registry=key_registry_merged,
                    get_private_key=get_private_key_fn,
                    capability_policy=capability_policy,
                )
        elif not is_scale_task and llm_backend == "ollama_live":
            from labtrust_gym.baselines.llm.agent import LLMAgentWithShield
            from labtrust_gym.baselines.llm.backends.ollama_live import (
                OllamaLiveBackend,
            )
            from labtrust_gym.engine.rbac import load_rbac_policy
            from labtrust_gym.security.agent_capabilities import load_agent_capabilities

            rbac_path = (
                (repo_root or Path.cwd()) / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
            )
            rbac_policy = load_rbac_policy(rbac_path)
            capability_policy = load_agent_capabilities(repo_root or Path.cwd())
            pz_to_engine = _default_pz_to_engine(
                num_runners=num_runners, num_insiders=num_insiders
            )
            backend = OllamaLiveBackend()
            llm_backend_ref = backend
            for aid in llm_agents:
                if aid not in scripted_agents_map:
                    continue
                scripted_agents_map[aid] = LLMAgentWithShield(
                    backend=backend,
                    rbac_policy=rbac_policy,
                    pz_to_engine=pz_to_engine,
                    strict_signatures=use_strict_signatures,
                    key_registry=key_registry_merged,
                    get_private_key=get_private_key_fn,
                    capability_policy=capability_policy,
                )
        if not is_scale_task and task_name in ("TaskD", "TaskD_AdversarialDisruption"):
            from labtrust_gym.baselines.adversary import AdversaryAgent

            scripted_agents_map["adversary_0"] = AdversaryAgent()
        if not is_scale_task and task_name in ("TaskF", "TaskF_InsiderAndKeyMisuse"):
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
        comms_cfg = None
        if risk_injector_instance is not None and hasattr(
            risk_injector_instance, "get_comms_config"
        ):
            comms_cfg = risk_injector_instance.get_comms_config()
        metrics, _ = run_episode(
            task,
            ep_seed,
            env_factory,
            agents_map,
            log_path=log_path,
            initial_state_overrides=initial_state_overrides or None,
            coord_method=coord_method_instance,
            risk_injector=risk_injector_instance,
            comms_config=comms_cfg,
        )
        episodes_metrics.append({"seed": ep_seed, "metrics": metrics})

    policy_versions = _policy_versions(repo_root)
    git_hash = _git_commit_hash(repo_root)
    partner_id_result = partner_id
    policy_fingerprint_result = policy_fingerprint
    if coord_method:
        agent_baseline_id = f"coord_{coord_method}"
    elif llm_backend == "deterministic":
        agent_baseline_id = "llm_safe_v1"
    elif llm_backend == "openai_live":
        agent_baseline_id = "llm_live_openai_v1"
    else:
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
            "coord_method": coord_method,
            "injection_id": injection_id,
        },
        "policy_versions": policy_versions,
        "git_sha": git_hash,
        "git_commit_hash": git_hash,
        "partner_id": partner_id_result,
        "policy_fingerprint": policy_fingerprint_result,
        "agent_baseline_id": agent_baseline_id,
        "episodes": episodes_metrics,
    }
    tool_reg_fp = (initial_state_overrides or {}).get("tool_registry_fingerprint")
    if tool_reg_fp is not None:
        results["tool_registry_fingerprint"] = tool_reg_fp

    if llm_backend is not None:
        if llm_backend == "deterministic":
            results["metadata"] = {
                "llm_backend_id": "deterministic_constrained",
                "llm_model_id": "n/a",
                "llm_error_rate": 0.0,
                "mean_llm_latency_ms": None,
            }
        elif llm_backend == "openai_live" and llm_backend_ref is not None:
            agg = llm_backend_ref.get_aggregate_metrics()
            results["metadata"] = {
                "llm_backend_id": agg.get("backend_id"),
                "llm_model_id": agg.get("model_id"),
                "llm_error_rate": agg.get("error_rate"),
                "mean_llm_latency_ms": agg.get("mean_latency_ms"),
                "p50_llm_latency_ms": agg.get("p50_latency_ms"),
                "p95_llm_latency_ms": agg.get("p95_latency_ms"),
                "total_tokens": agg.get("total_tokens"),
                "tokens_per_step": agg.get("tokens_per_step"),
                "estimated_cost_usd": agg.get("estimated_cost_usd"),
            }
        elif llm_backend == "ollama_live" and llm_backend_ref is not None:
            agg = llm_backend_ref.get_aggregate_metrics()
            results["metadata"] = {
                "llm_backend_id": agg.get("backend_id"),
                "llm_model_id": agg.get("model_id"),
                "llm_error_rate": agg.get("error_rate"),
                "mean_llm_latency_ms": agg.get("mean_latency_ms"),
            }
        else:
            results["metadata"] = {
                "llm_backend_id": llm_backend,
                "llm_model_id": None,
                "llm_error_rate": None,
                "mean_llm_latency_ms": None,
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
