"""
Benchmark runner: run N episodes for a task, record metrics, output JSON.

Flow: run_benchmark builds env/agents, then for each episode calls run_episode;
episode metrics are collected, then the results payload is built (with optional
LLM/coordination metadata), validated against results.v0.2 schema, and written.
Writes results.json with metadata: git commit, policy versions, seeds, config,
run_duration_wall_s, python_version, platform. When coordination is used,
writes coord_decisions.jsonl (contract v0.1) per episode.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

# Callback (actions_dict, action_infos) -> (approved_actions_dict, approved_action_infos) | None. None = pass through.
ApprovalCallback = Callable[
    [dict[str, Any], dict[str, dict[str, Any]]],
    tuple[dict[str, Any], dict[str, dict[str, Any]]] | None,
]

from labtrust_gym.benchmarks.env_protocol import BenchmarkEnv

_LOG = logging.getLogger(__name__)

from labtrust_gym.baselines.coordination.llm_executor import (
    _proposal_hash,
    shield_outcome_hash_from_step_results,
)
from labtrust_gym.benchmarks.metrics import (
    compute_episode_metrics,
    get_metrics_aggregator,
)
from labtrust_gym.benchmarks.result_builder import normalize_llm_economics
from labtrust_gym.benchmarks.summarize import (
    RESULTS_SCHEMA_VERSION,
    validate_results_v02,
)
from labtrust_gym.benchmarks.tasks import BenchmarkTask, get_task
from labtrust_gym.logging.episode_log import (
    EpisodeLogger,
    build_llm_coord_audit_digest_entry,
    build_llm_coord_proposal_entry,
)
from labtrust_gym.util.json_utils import canonical_json


def _git_commit_hash(cwd: Path | None = None) -> str | None:
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
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        _LOG.debug("Git rev-parse failed: %s", e)
    return None


def _policy_versions(root: Path) -> dict[str, str]:
    """Read policy file versions (emits vocab, catalogue schema, etc.)."""
    versions: dict[str, str] = {}
    emits_path = root / "policy" / "emits" / "emits_vocab.v0.1.yaml"
    if emits_path.exists():
        try:
            data = emits_path.read_text(encoding="utf-8")
            for line in data.splitlines()[:20]:
                if "version:" in line:
                    versions["emits_vocab"] = line.split("version:")[-1].strip().strip('"')
                    break
        except Exception as e:
            _LOG.warning("Failed to read emits_vocab version, using unknown: %s", e)
            versions["emits_vocab"] = "unknown"
    catalogue_path = root / "policy" / "schemas" / "test_catalogue.schema.v0.1.json"
    if catalogue_path.exists():
        try:
            data = json.loads(catalogue_path.read_text(encoding="utf-8"))
            versions["catalogue_schema"] = data.get("schema_version", "unknown")
        except Exception as e:
            _LOG.warning("Failed to read catalogue_schema version, using unknown: %s", e)
            versions["catalogue_schema"] = "unknown"
    return versions


def run_episode(
    task: BenchmarkTask,
    episode_seed: int,
    env_factory: Any,
    scripted_agents_map: dict[str, Any] | None = None,
    log_path: Path | None = None,
    initial_state_overrides: dict[str, Any] | None = None,
    coord_method: Any | None = None,
    risk_injector: Any | None = None,
    comms_config: Any | None = None,
    episode_id: int = 0,
    run_dir: Path | None = None,
    metrics_aggregator_id: str | None = None,
    repo_root: Path | None = None,
    env: BenchmarkEnv | None = None,
    log_step_interval: int | None = None,
    checkpoint_every_n_steps: int | None = None,
    run_dir_for_checkpoint: Path | None = None,
    base_seed_for_checkpoint: int = 0,
    num_episodes_for_checkpoint: int = 0,
    approval_callback: ApprovalCallback | None = None,
) -> tuple[dict[str, Any], list[list[dict[str, Any]]]]:
    """
    Run one episode. Returns (metrics_dict, step_results_per_step).

    env_factory: callable(initial_state, reward_config, log_path=?) -> env; used only when env is None.
    scripted_agents_map: agent_id -> agent with .act(obs, agent_id) -> (idx, info).
    log_path: optional JSONL path for episode step log (append mode).
    initial_state_overrides: optional dict merged into initial_state (e.g. timing_mode, ablations).
    coord_method: optional CoordinationMethod; when set, propose_actions drives all agents (coord_scale/coord_risk).
    run_dir: optional; when set, passed to coord_method.reset via scale_config for study-track artifacts.
    repo_root: optional policy root; when set, passed to task.get_initial_state as policy_root.
    env: optional existing env instance; when provided, it is reset with this episode's initial_state instead of
        creating a new env via env_factory. Use for benchmark throughput (same task/config across episodes).

    For coord_risk (coordination + risk injectors), see docs/risk-and-security/security_flows_and_entry_points.md.
    Data flow (runner owns env): docs/coordination/coordination_and_env.md.
    """
    calibration = initial_state_overrides.get("calibration") if initial_state_overrides else None
    initial_state = task.get_initial_state(episode_seed, calibration=calibration, policy_root=repo_root)
    if initial_state_overrides:
        initial_state = {**initial_state, **initial_state_overrides}
    if env is not None:
        obs, _ = env.reset(
            seed=episode_seed,
            options={"initial_state": initial_state},
        )
    else:
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
    scale_config_dict: dict[str, Any] = {}
    if hasattr(task, "scale_config") and task.scale_config is not None:
        from dataclasses import asdict

        scale_config_dict = asdict(task.scale_config)
    if initial_state.get("injection_id"):
        scale_config_dict = dict(scale_config_dict)
        scale_config_dict["injection_id"] = initial_state["injection_id"]
    if run_dir is not None:
        scale_config_dict = dict(scale_config_dict)
        scale_config_dict["run_dir"] = str(run_dir)
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
                    str(initial_state.get("timing_mode", "explicit")).strip().lower() or "explicit",
                )
    step_results_per_step: list[list[dict[str, Any]]] = []
    t_s_list: list[int] = []
    dt_s = env.get_dt_s()
    coord_decisions_path: Path | None = None
    episode_logger_llm: EpisodeLogger | None = None
    llm_audit_steps: list[dict[str, Any]] = []
    if coord_method is not None and log_path is not None:
        coord_decisions_path = log_path.parent / "coord_decisions.jsonl"
        coord_decisions_path.write_text("", encoding="utf-8")
        episode_logger_llm = EpisodeLogger(path=log_path)
    timing_mode = str(initial_state.get("timing_mode", "explicit")).strip().lower()
    if timing_mode not in ("explicit", "simulated"):
        timing_mode = "explicit"
    queue_lengths_per_step: list[dict[str, int]] = []
    infos: dict[str, dict[str, Any]] = {}
    total_critical_episode = 0
    stale_count_episode = 0
    view_ages_ms_episode: list[float] = []
    dt_ms = 10000.0

    blackboard_harness: Any | None = None
    if coord_method is not None and (getattr(task, "scale_config", None) is not None):
        from labtrust_gym.coordination.comms_model import CommsConfig
        from labtrust_gym.coordination.harness import BlackboardHarness

        agent_ids = list(env.agents)
        device_ids = env.get_device_ids()
        zone_ids = env.get_zone_ids()
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
        dt_ms = float(env.get_dt_s()) * 1000.0

    for step_t in range(task.max_steps):
        view_ages_ms_step: list[float] = []
        obs_for_step = obs
        audit_obs: dict[str, Any] | None = None
        if risk_injector is not None:
            obs_for_step, audit_obs = risk_injector.mutate_obs(obs)
        actions: dict[str, Any] = {}
        action_infos: dict[str, dict[str, Any]] = {}
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
            elif (
                getattr(coord_method, "_max_repairs", 0) > 0
                and getattr(coord_method, "_backend", None) is not None
                and callable(
                    getattr(
                        getattr(coord_method, "_backend", None),
                        "generate_proposal",
                        None,
                    )
                )
            ):
                from labtrust_gym.baselines.coordination.llm_contract import (
                    validate_proposal,
                )
                from labtrust_gym.baselines.coordination.llm_executor import (
                    execute_proposal_shield_only,
                    get_actions_from_proposal,
                    run_proposal_with_repair,
                )
                from labtrust_gym.baselines.coordination.state_digest import (
                    build_state_digest,
                )
                from labtrust_gym.baselines.llm.shield import apply_shield

                rbac_policy = getattr(coord_method, "_rbac_policy", None) or {}
                policy_summary_repair = getattr(coord_method, "_policy_summary", None) or effective_policy or {}
                allowed_repair = getattr(coord_method, "_allowed_actions", None) or ["NOOP", "TICK"]
                backend_repair = getattr(coord_method, "_backend", None)

                def _propose_fn(
                    obs: dict[str, Any],
                    infos: dict[str, dict[str, Any]],
                    t: int,
                    repair_request: dict[str, Any] | None = None,
                ) -> dict[str, Any] | None:
                    digest = build_state_digest(obs, infos, t, policy_summary_repair)
                    if getattr(coord_method, "_prompt_fingerprints", None) is None:
                        try:
                            from labtrust_gym.baselines.coordination.prompt_fingerprint import (
                                compute_prompt_fingerprints,
                            )

                            coord_method._prompt_fingerprints = compute_prompt_fingerprints(
                                method_id=coord_method.method_id,
                                state_digest=digest,
                                allowed_actions=allowed_repair,
                                policy=policy_summary_repair,
                                repo_root=None,
                            )
                        except Exception as e:
                            _LOG.debug("Repair fingerprint update failed, clearing: %s", e)
                            coord_method._prompt_fingerprints = {}
                    gen = getattr(backend_repair, "generate_proposal", None)
                    if not callable(gen):
                        return None
                    out = gen(
                        digest,
                        allowed_repair,
                        step_id=t,
                        method_id=coord_method.method_id,
                    )
                    if isinstance(out, tuple):
                        proposal, meta = out[0], out[1]
                    else:
                        proposal = out
                        meta = {}
                    coord_method._last_proposal = proposal
                    coord_method._last_meta = meta
                    coord_method._proposal_total_count += 1
                    lat = meta.get("latency_ms")
                    if lat is not None and isinstance(lat, (int, float)):
                        coord_method._latency_ms_list.append(float(lat))
                    return proposal

                def _validate_fn(proposal: dict[str, Any]) -> tuple[bool, list[str]]:
                    valid, errors = validate_proposal(
                        proposal,
                        allowed_actions=allowed_repair,
                        strict_reason_codes=False,
                    )
                    return valid, errors

                def _log_attempt_fn(record: dict[str, Any]) -> None:
                    if episode_logger_llm is not None and record.get("log_type") == "LLM_COORD_PROPOSAL_ATTEMPT":
                        episode_logger_llm.log_llm_coord_proposal(record)

                final_proposal, report, _attempt_count = run_proposal_with_repair(
                    _propose_fn,
                    env,
                    apply_shield,
                    rbac_policy,
                    policy_summary_repair,
                    obs_for_step,
                    infos,
                    step_t,
                    validate_fn=_validate_fn,
                    capability_profile=None,
                    max_repairs=coord_method._max_repairs,
                    blocked_threshold=coord_method._blocked_threshold,
                    log_attempt_fn=_log_attempt_fn if episode_logger_llm else None,
                    execute_fn=execute_proposal_shield_only,
                )
                if final_proposal is None or report is None:
                    actions_dict = {a: {"action_index": 0} for a in env.agents}
                else:
                    actions_repair, action_infos_repair = get_actions_from_proposal(
                        env,
                        final_proposal,
                        apply_shield,
                        rbac_policy,
                        policy_summary_repair,
                        None,
                    )
                    actions_dict = {
                        aid: {
                            "action_index": actions_repair[aid],
                            **(action_infos_repair.get(aid) or {}),
                        }
                        for aid in env.agents
                    }
            else:
                # When N <= N_max, only propose_actions (or step) is used; combine_submissions is never called.
                n_max = int(scale_config_dict.get("coord_propose_actions_max_agents", 50))
                use_combine = len(env.agents) > n_max and hasattr(coord_method, "combine_submissions")
                if use_combine:
                    submissions_shape = "action"
                    if repo_root is not None:
                        try:
                            from labtrust_gym.policy.coordination import (
                                get_submission_shape,
                                load_coordination_methods,
                                load_submission_shapes,
                            )

                            shapes = load_submission_shapes(repo_root=repo_root)
                            methods_reg = {}
                            _reg_path = repo_root / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
                            if _reg_path.exists():
                                methods_reg = load_coordination_methods(_reg_path) or {}
                            method_id = getattr(coord_method, "method_id", "unknown")
                            submissions_shape = get_submission_shape(
                                method_id, shapes=shapes, methods_registry=methods_reg
                            )
                        except Exception as e:
                            _LOG.debug("Submission shape lookup failed, using action: %s", e)
                    try:
                        from labtrust_gym.policy.coordination import adapt_submission
                    except ImportError:
                        adapt_submission = None
                    submissions: dict[str, dict[str, Any]] = {}
                    for agent_id in env.agents:
                        if scripted_agents_map and agent_id in scripted_agents_map:
                            agent = scripted_agents_map[agent_id]
                            ret = agent.act(obs_for_step.get(agent_id, {}), agent_id)
                            action_index = ret[0]
                            action_info = ret[1] if len(ret) > 1 else {}
                            if adapt_submission is not None:
                                submissions[agent_id] = adapt_submission(submissions_shape, action_index, action_info)
                            else:
                                submissions[agent_id] = {
                                    "action_index": action_index,
                                    **action_info,
                                }
                        else:
                            submissions[agent_id] = {"action_index": 0}
                    actions_dict = coord_method.combine_submissions(submissions, obs_for_step, infos, step_t)
                else:
                    if os.environ.get("LABTRUST_DEBUG_COORD_QUEUES") == "1" and step_t < 3 and obs_for_step:
                        _first_agent = next(iter(obs_for_step), None)
                        if _first_agent:
                            _o = obs_for_step.get(_first_agent) or {}
                            _qbd = _o.get("queue_by_device") or []
                            _non_empty = sum(1 for _d in _qbd if (_d or {}).get("queue_head"))
                            _LOG.warning(
                                "[LABTRUST_DEBUG_COORD_QUEUES] step=%s agent=%s "
                                "queue_by_device_len=%s non_empty_queue_head=%s",
                                step_t,
                                _first_agent,
                                len(_qbd),
                                _non_empty,
                            )
                    inj_id = getattr(risk_injector, "injection_id", None) if risk_injector is not None else None
                    if getattr(coord_method, "method_id", None) == "llm_repair_over_kernel_whca" and inj_id in (
                        "INJ-COMMS-POISON-001",
                        "INJ-ID-SPOOF-001",
                    ):
                        infos = dict(infos) if isinstance(infos, dict) else {}
                        infos["_coord_repair_triggers"] = (
                            ["comms_poison"] if inj_id == "INJ-COMMS-POISON-001" else ["id_spoof"]
                        )
                    actions_dict = coord_method.propose_actions(obs_for_step, infos, step_t)
            if run_dir is not None:
                try:
                    from labtrust_gym.baselines.coordination.trace import (
                        append_trace_event,
                        trace_from_contract_record,
                    )

                    trace_path = Path(run_dir) / "METHOD_TRACE.jsonl"
                    method_id = getattr(coord_method, "method_id", "unknown")
                    event = trace_from_contract_record(method_id, step_t, actions_dict)
                    append_trace_event(trace_path, event)
                except Exception as e:
                    _LOG.debug("METHOD_TRACE append skipped: %s", e)
            if (
                coord_method is not None
                and scale_config_dict.get("apply_runner_shield_on_propose_actions")
                and actions_dict
                and effective_policy
            ):
                try:
                    from labtrust_gym.baselines.llm.shield import apply_shield
                    from labtrust_gym.envs.action_contract import (
                        ACTION_INDEX_TO_TYPE,
                    )

                    rbac_policy = effective_policy.get("rbac_policy") or {}
                    roles_map = rbac_policy.get("roles") or {}
                    agents_map = rbac_policy.get("agents") or {}
                    type_to_index = {v: k for k, v in ACTION_INDEX_TO_TYPE.items()}
                    shielded: dict[str, Any] = {}
                    for agent_id in env.agents:
                        ad = actions_dict.get(agent_id, {"action_index": 0})
                        action_type = ad.get("action_type") or ACTION_INDEX_TO_TYPE.get(
                            ad.get("action_index", 0), "NOOP"
                        )
                        candidate = {
                            "action_type": action_type,
                            "args": ad.get("args") or {},
                            "reason_code": ad.get("reason_code"),
                            "token_refs": ad.get("token_refs") or [],
                            "rationale": ad.get("rationale", ""),
                            "key_id": ad.get("key_id"),
                            "signature": ad.get("signature"),
                        }
                        role_id = agents_map.get(agent_id) if isinstance(agents_map, dict) else None
                        role_def = roles_map.get(role_id) if isinstance(roles_map, dict) and role_id else None
                        allowed_actions = (
                            list(role_def.get("allowed_actions"))
                            if isinstance(role_def, dict) and isinstance(role_def.get("allowed_actions"), list)
                            else []
                        )
                        policy_summary = {
                            "allowed_actions": allowed_actions,
                            "strict_signatures": effective_policy.get("strict_signatures", False),
                        }
                        safe_action, _filtered, _rc = apply_shield(
                            candidate, agent_id, rbac_policy, policy_summary, None
                        )
                        idx = type_to_index.get(safe_action.get("action_type", "NOOP"), 0)
                        shielded[agent_id] = {
                            "action_index": idx,
                            "action_type": safe_action.get("action_type", "NOOP"),
                            "args": safe_action.get("args") or {},
                            "reason_code": safe_action.get("reason_code"),
                            "token_refs": safe_action.get("token_refs") or [],
                            "rationale": safe_action.get("rationale", ""),
                        }
                    actions_dict = shielded
                except Exception as e:
                    _LOG.warning("Runner-level shield on propose_actions failed: %s", e)
            if risk_injector is not None:
                actions_dict, audit_actions = risk_injector.mutate_actions(actions_dict)
            else:
                audit_actions = []
            if approval_callback is not None:
                _built_infos: dict[str, dict[str, Any]] = {}
                for _aid in env.agents:
                    _ad = actions_dict.get(_aid, {"action_index": 0})
                    _, _info = action_dict_to_index_and_info(_ad)
                    _built_infos[_aid] = dict(_info) if _info else {}
                _out = approval_callback(actions_dict, _built_infos)
                if _out is not None:
                    actions_dict, _ = _out
            for agent_id in env.agents:
                ad = actions_dict.get(agent_id, {"action_index": 0})
                idx, info = action_dict_to_index_and_info(ad)
                actions[agent_id] = idx
                if info:
                    action_infos[agent_id] = dict(info)
            # Coordination timing: detect stale decisions (critical actions on old view)
            stale_emit_payloads_this_step: list[dict[str, Any]] = []
            if blackboard_harness is not None:
                from labtrust_gym.coordination.coordination_monitor import (
                    DEFAULT_MAX_STALENESS_MS,
                    check_staleness,
                    count_critical_actions,
                )

                view_snapshots = blackboard_harness.view_snapshots()
                stale_count_step, stale_emit_payloads_this_step, view_ages_ms_step = check_staleness(
                    actions_dict,
                    view_snapshots,
                    step_t,
                    dt_ms=dt_ms,
                    max_staleness_ms=DEFAULT_MAX_STALENESS_MS,
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
            if approval_callback is not None:
                _built_infos_scripted: dict[str, dict[str, Any]] = {}
                for _aid in env.agents:
                    _ad = actions_dict.get(_aid, {"action_index": 0})
                    _built_infos_scripted[_aid] = {
                        k: v for k, v in _ad.items() if k != "action_index" and v is not None
                    }
                _out_scripted = approval_callback(actions_dict, _built_infos_scripted)
                if _out_scripted is not None:
                    actions_dict, _ = _out_scripted
            for agent_id in env.agents:
                ad = actions_dict.get(agent_id, {"action_index": 0})
                actions[agent_id] = ad.get("action_index", 0)
                action_infos[agent_id] = {k: v for k, v in ad.items() if k != "action_index" and v is not None}
        obs, rewards, term, trunc, infos = env.step(actions, action_infos=action_infos)
        first_agent = list(env.agents)[0] if env.agents else None
        step_results = list(infos.get(first_agent, {}).get("_benchmark_step_results", []) if first_agent else [])
        agent_list_step = list(env.agents)
        shield_outcome_hash_this_step = ""
        if coord_method is not None and agent_list_step:
            shield_outcome_hash_this_step = shield_outcome_hash_from_step_results(
                step_results[: len(agent_list_step)],
                agent_list_step,
            )
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
            detector_emits = getattr(coord_method, "last_detector_emits", None)
            if detector_emits:
                step_results.extend(detector_emits)
        if risk_injector is not None:
            step_results.extend(audit_actions)
            if audit_obs is not None:
                step_results.append(audit_obs)
            extra = risk_injector.observe_step(step_results)
            step_results.extend(extra)
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
            invariants_considered: list[str] = []
            if shield_emits:
                try:
                    from labtrust_gym.baselines.coordination.routing.invariants import (
                        INV_ROUTE_001,
                        INV_ROUTE_002,
                        INV_ROUTE_SWAP,
                    )

                    invariants_considered = [INV_ROUTE_001, INV_ROUTE_002, INV_ROUTE_SWAP]
                except Exception as e:
                    _LOG.warning("Failed to load invariants_considered, using None: %s", e)
            contract_record = build_contract_record(
                method_id=coord_method.method_id,
                t_step=step_t,
                actions_dict=actions_dict,
                view_age_ms=view_age_ms,
                view_age_ms_per_agent=view_age_ms_per_agent,
                plan_time_ms=None,
                invariants_considered=invariants_considered or None,
                safety_shield_applied=bool(shield_emits),
                safety_shield_details=({"count": len(shield_emits)} if shield_emits else None),
            )
            if os.environ.get("LABTRUST_STRICT_COORD_CONTRACT") == "1":
                errs = validate_contract_record(contract_record)
                if errs:
                    raise ValueError(f"Coord contract validation failed at step {step_t}: {errs}")
            with coord_decisions_path.open("a", encoding="utf-8") as f:
                f.write(serialize_contract_record(contract_record))
        if episode_logger_llm is not None:
            last_proposal = getattr(coord_method, "_last_proposal", None)
            last_meta = getattr(coord_method, "_last_meta", None)
            if last_proposal is not None and last_meta is not None:
                prop_hash = _proposal_hash(last_proposal)
                shield_hash = (
                    shield_outcome_hash_this_step or getattr(coord_method, "last_shield_outcome_hash", None) or ""
                )
                assurance_evidence: list[dict[str, Any]] | None = None
                shield_emits_for_evidence = getattr(coord_method, "last_shield_emits", None) or []
                for emit_item in shield_emits_for_evidence:
                    payload = emit_item.get("coord_shield_payload") if isinstance(emit_item, dict) else None
                    if payload and payload.get("assurance_evidence") is not None:
                        assurance_evidence = payload["assurance_evidence"]
                        break
                record = build_llm_coord_proposal_entry(
                    proposal_id=last_proposal.get("proposal_id", ""),
                    step_id=step_t,
                    canonical_proposal_hash=prop_hash,
                    meta=last_meta,
                    shield_outcome_hash=(shield_hash if shield_hash else None),
                    assurance_evidence=assurance_evidence,
                )
                episode_logger_llm.log_llm_coord_proposal(record)
                llm_audit_steps.append(
                    {
                        "step_id": step_t,
                        "proposal_hash": prop_hash,
                        "shield_outcome_hash": shield_hash,
                    }
                )
        step_results_per_step.append(step_results)
        if coord_method is not None and hasattr(coord_method, "on_step_result"):
            coord_method.on_step_result(step_results)
        t_s_list.append(len(step_results_per_step) * dt_s)
        if log_path is not None and run_dir is not None and log_step_interval is not None and log_step_interval > 0:
            step_idx = len(step_results_per_step) - 1
            if (step_idx + 1) % log_step_interval == 0:
                t_s = t_s_list[-1] if t_s_list else 0
                violations_n = sum(1 for r in step_results if r.get("status") == "BLOCKED") + sum(
                    len(r.get("violations") or []) for r in step_results
                )
                steps_jsonl = run_dir / "steps.jsonl"
                step_record = {
                    "episode": episode_id,
                    "step": step_idx,
                    "t_s": t_s,
                    "violations": violations_n,
                }
                with open(steps_jsonl, "a", encoding="utf-8") as sf:
                    sf.write(json.dumps(step_record, sort_keys=True) + "\n")
        if (
            checkpoint_every_n_steps is not None
            and checkpoint_every_n_steps > 0
            and run_dir_for_checkpoint is not None
            and (step_idx + 1) % checkpoint_every_n_steps == 0
        ):
            try:
                from labtrust_gym.benchmarks.checkpoint import (
                    write_step_checkpoint,
                )

                env_state = None
                if env is not None and hasattr(env, "get_state"):
                    env_state = env.get_state()
                write_step_checkpoint(
                    run_dir_for_checkpoint,
                    episode_index=episode_id,
                    step_index=step_idx,
                    base_seed=base_seed_for_checkpoint,
                    num_episodes=num_episodes_for_checkpoint,
                    env_state=env_state,
                    rng_state=env_state.get("rng_state") if env_state else None,
                )
            except Exception:
                pass
        if (
            timing_mode == "simulated"
            and hasattr(env, "get_device_queue_lengths")
            and callable(getattr(env, "get_device_queue_lengths", None))
        ):
            q_per_dev = env.get_device_queue_lengths()
            if q_per_dev:
                queue_lengths_per_step.append(q_per_dev)

    timing_summary: dict[str, Any] = {}
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
    aggregator = get_metrics_aggregator(metrics_aggregator_id) if metrics_aggregator_id else None
    compute_fn = aggregator if aggregator is not None else compute_episode_metrics
    metrics = compute_fn(
        step_results_per_step,
        t_s_per_step=t_s_list,
        sla_turnaround_s=task.sla_turnaround_s,
        attack_start_step=getattr(task, "attack_start_step", None),
        insider_attack_steps=getattr(task, "insider_attack_steps", None),
        timing_mode=timing_summary.get("timing_mode", timing_mode),
        episode_time_s=episode_time_s,
        device_busy_s=device_busy_s if device_busy_s else None,
        queue_lengths_per_step=(queue_lengths_per_step if queue_lengths_per_step else None),
        injection_metrics=injection_metrics,
        injection_id=injection_id,
    )
    if comm_metrics is not None:
        metrics["coordination"] = {"comm": comm_metrics}
    if coord_method is not None:
        method_comm = getattr(coord_method, "get_comm_metrics", lambda: None)()
        if method_comm:
            metrics.setdefault("coordination", {})["comm"] = {
                **(metrics.get("coordination", {}).get("comm") or {}),
                **method_comm,
            }
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
        sched_metrics = getattr(coord_method, "get_schedule_metrics", lambda: None)()
        if sched_metrics is not None:
            metrics.setdefault("coordination", {})["sched"] = sched_metrics
        hierarchy_metrics = getattr(coord_method, "get_hierarchy_metrics", lambda: None)()
        if hierarchy_metrics is not None:
            metrics.setdefault("coordination", {})["hierarchy"] = hierarchy_metrics
        llm_metrics = getattr(coord_method, "get_llm_metrics", lambda: None)()
        llm_repair_metrics = getattr(coord_method, "get_llm_repair_metrics", lambda: None)()
        if llm_repair_metrics is not None:
            metrics.setdefault("coordination", {})["llm_repair"] = llm_repair_metrics
        if llm_metrics is not None or llm_repair_metrics is not None:
            steps_count = metrics.get("steps", 1)
            metrics.setdefault("coordination", {})["llm"] = normalize_llm_economics(
                llm_metrics, llm_repair_metrics, steps_count
            )
        auction_metrics = getattr(coord_method, "get_auction_metrics", lambda: None)()
        if auction_metrics is not None:
            metrics.setdefault("coordination", {})["auction"] = auction_metrics
        detection_events = getattr(coord_method, "get_detection_events", lambda: [])()
        drop_reasons = getattr(coord_method, "get_drop_reasons", lambda: [])()
        if detection_events or drop_reasons:
            metrics.setdefault("coordination", {})["gossip_comms"] = {
                "detection_events": detection_events,
                "drop_reasons": drop_reasons,
            }
        detector_metrics = getattr(coord_method, "get_detector_metrics", lambda: None)()
        if detector_metrics is not None:
            dm = detector_metrics
            if "sec" not in metrics:
                metrics["sec"] = {}
            metrics["sec"]["detector_recommendation_rate"] = dm.get("detector_recommendation_rate")
            metrics["sec"]["detector_invalid_recommendation_rate"] = dm.get("detector_invalid_recommendation_rate")
            suspected_steps = dm.get("detector_suspected_at_steps") or []
            first_app = (injection_metrics or {}).get("first_application_step")
            if injection_id and first_app is not None:
                metrics["sec"]["detector_true_positive_proxy"] = (
                    1.0 if any(s >= first_app for s in suspected_steps) else 0.0
                )
            else:
                metrics["sec"]["detector_true_positive_proxy"] = 0.0
            if not injection_id and suspected_steps:
                metrics["sec"]["detector_false_positive_proxy"] = 1.0
            else:
                metrics["sec"]["detector_false_positive_proxy"] = 0.0
    if coord_method is not None:
        on_episode_end = getattr(coord_method, "on_episode_end", None)
        if callable(on_episode_end):
            metrics_for_callback = dict(metrics)
            metrics_for_callback["_episode_id"] = episode_id
            on_episode_end(metrics_for_callback)
    if episode_logger_llm is not None:
        if llm_audit_steps:
            digest_record = build_llm_coord_audit_digest_entry(
                episode_id=episode_id,
                steps=llm_audit_steps,
            )
            episode_logger_llm.log_llm_coord_proposal(digest_record)
        episode_logger_llm.close()
    return metrics, step_results_per_step


def _default_pz_to_engine(num_runners: int = 2, num_insiders: int = 0) -> dict[str, str]:
    """Standard PZ agent -> engine agent_id mapping (matches LabTrustParallelEnv default)."""
    d: dict[str, str] = {"ops_0": "A_OPS_0"}
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
    env_factory: Any | None = None,
    scripted_agents_map: dict[str, Any] | None = None,
    repo_root: Path | None = None,
    log_path: Path | None = None,
    initial_state_overrides: dict[str, Any] | None = None,
    partner_id: str | None = None,
    use_llm_safe_v1_ops: bool = False,
    use_llm_live_openai: bool = False,
    llm_backend: str | None = None,
    llm_agents: list[str] | None = None,
    llm_output_mode: str = "json_schema",
    timing_mode: str | None = None,
    coord_method: str | None = None,
    injection_id: str | None = None,
    injection_phase: str | None = None,
    early_step_cap: int | None = None,
    late_step_min: int | None = None,
    scale_config_override: Any | None = None,
    pipeline_mode: str | None = None,
    allow_network: bool | None = None,
    llm_trace_collector: Any | None = None,
    llm_model: str | None = None,
    metrics_aggregator_id: str | None = None,
    domain_id: str | None = None,
    record_fixtures_path: Path | None = None,
    record_coord_fixtures_path: Path | None = None,
    coord_fixtures_path: Path | None = None,
    coord_planner_backend: str | None = None,
    coord_bidder_backend: str | None = None,
    coord_repair_backend: str | None = None,
    coord_detector_backend: str | None = None,
    coord_planner_model: str | None = None,
    coord_bidder_model: str | None = None,
    coord_repair_model: str | None = None,
    coord_detector_model: str | None = None,
    coord_proposal_backend_override: Any | None = None,
    agent_driven: bool = False,
    multi_agentic: bool = False,
    use_parallel_multi_agentic: bool = False,
    round_timeout_s: float = 60.0,
    parallel_multi_agentic_max_workers: int | None = None,
    checkpoint_every_n_episodes: int | None = None,
    resume_from: Path | None = None,
    log_step_interval: int | None = None,
    checkpoint_every_n_steps: int | None = None,
    progress_callback: Callable[[int, int, dict[str, Any]], None] | None = None,
    always_record_step_timing: bool = False,
    approval_callback: ApprovalCallback | None = None,
) -> dict[str, Any]:
    """
    Run N episodes for the task, write results.json.

    Returns the full results dict (also written to out_path).
    log_path: optional JSONL path for episode step log (truncated at start).
    initial_state_overrides: optional dict merged into each episode initial_state (e.g. timing_mode).
    partner_id: optional partner overlay ID; effective_policy and policy_fingerprint injected into initial_state.
    llm_backend: optional "deterministic" | "openai_live" | "openai_responses" | "ollama_live" to use LLM for agents or coordination; None = scripted / deterministic.
    llm_model: optional model id when using openai_live (e.g. gpt-4o); overrides LABTRUST_OPENAI_MODEL.
    llm_agents: agent IDs that use LLM (e.g. ["ops_0"] or ["ops_0", "runner_0"]). Default ["ops_0"] when llm_backend set.
    llm_output_mode: for openai_responses backend, "json_schema" (default) or "tool_call".
    timing_mode: optional "explicit" | "simulated"; overrides task default and initial_state_overrides.
    coord_method: optional coordination method_id for coord_scale / coord_risk (e.g. centralized_planner).
    injection_id: optional risk injection id for coord_risk (e.g. INJ-ID-SPOOF-001); loads config from study spec.
    injection_phase: optional application phase override (early | mid | late | full) for the injector; overrides spec.
    early_step_cap: optional step cap for early phase; overrides spec when set.
    late_step_min: optional step min for late phase; overrides spec when set.
    scale_config_override: optional CoordinationScaleConfig for coord_scale/coord_risk; when set, overrides task scale and horizon.
    pipeline_mode: optional "deterministic" | "llm_offline" | "llm_live"; when set, configures pipeline and enforces network gating.
    allow_network: optional; when True and pipeline_mode is llm_live, allows live LLM backends.
    llm_trace_collector: optional; when set, live LLM backends record redacted requests/responses/fingerprints/usage for LLM_TRACE bundle.
    domain_id: optional; when set, use get_domain_adapter_factory(domain_id) to build the env engine (default hospital_lab when unset).
    agent_driven: when True, run episodes in agent-centric mode (backend.run_episode(driver)); requires coord_method and uses step_lab tool.
    checkpoint_every_n_episodes: when set and run_dir is set (from log_path or out_path parent), write a checkpoint after every N episodes for resume.
    resume_from: when set, load checkpoint from this dir and skip episodes already done (start from episodes_done). Use with same task/seed/episodes as original run.
    log_step_interval: when set with log_path, append a compact step record to run_dir/steps.jsonl every N steps (1 = every step, 0 = off).
    checkpoint_every_n_steps: when set with run_dir (from log_path), write a step checkpoint every N steps for best-effort resume.
    """
    from labtrust_gym.pipeline import (
        PipelineMode,
        get_llm_backend_id,
        get_pipeline_mode,
        print_startup_banner,
        require_llm_live_allow_network,
        set_pipeline_config,
    )

    if llm_backend is None and use_llm_live_openai:
        llm_backend = "openai_live"
    if llm_backend is None and use_llm_safe_v1_ops:
        llm_backend = "deterministic_constrained"
    if llm_agents is None and llm_backend is not None:
        llm_agents = ["ops_0"]
    llm_agents = llm_agents or []

    # Resolve pipeline_mode and allow_network. Only three valid modes: deterministic | llm_offline | llm_live (see pipeline.py and docs/agents/llm_live.md).
    if pipeline_mode is not None and pipeline_mode not in (
        "deterministic",
        "llm_offline",
        "llm_live",
    ):
        raise ValueError(f"pipeline_mode must be deterministic, llm_offline, or llm_live, got {pipeline_mode!r}")
    if pipeline_mode is None:
        if llm_backend is None:
            pipeline_mode = "deterministic"
        elif llm_backend in ("deterministic", "deterministic_constrained"):
            pipeline_mode = "llm_offline"
        else:
            pipeline_mode = "llm_live"
    _live_backends = ("openai_live", "openai_responses", "ollama_live", "anthropic_live", "openai_hosted")
    if pipeline_mode == "deterministic" and llm_backend in _live_backends:
        raise ValueError(
            "pipeline_mode=deterministic does not allow live LLM backends. "
            "Use --pipeline-mode llm_live and --allow-network to use openai_live, openai_responses, ollama_live, or anthropic_live."
        )
    if pipeline_mode == "llm_offline" and llm_backend in _live_backends:
        raise ValueError(
            "pipeline_mode=llm_offline allows only the deterministic LLM backend (no network). "
            "Use --llm-backend deterministic for offline LLM, or --pipeline-mode llm_live and --allow-network for live."
        )
    if allow_network is None:
        allow_network = False
    llm_backend_id_for_banner: str | None = None
    if llm_backend == "deterministic":
        llm_backend_id_for_banner = "fixture"
    elif llm_backend == "deterministic_constrained":
        llm_backend_id_for_banner = "deterministic_constrained"
    elif llm_backend == "openai_live":
        llm_backend_id_for_banner = "openai_live"
    elif llm_backend == "openai_responses":
        llm_backend_id_for_banner = "openai_responses"
    elif llm_backend == "ollama_live":
        llm_backend_id_for_banner = "ollama_live"
    elif llm_backend == "anthropic_live":
        llm_backend_id_for_banner = "anthropic_live"
    elif llm_backend == "openai_hosted":
        llm_backend_id_for_banner = "openai_hosted"
    set_pipeline_config(
        pipeline_mode=cast(PipelineMode, pipeline_mode),
        allow_network=allow_network,
        llm_backend_id=llm_backend_id_for_banner,
    )
    if pipeline_mode == "llm_live" and llm_backend in (
        "openai_live",
        "openai_responses",
        "ollama_live",
        "anthropic_live",
        "openai_hosted",
    ):
        require_llm_live_allow_network()
    print_startup_banner()

    llm_backend_ref: Any = None
    if not task_name or not isinstance(task_name, str):
        raise ValueError(f"task_name must be a non-empty string, got {task_name!r}")
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
    overrides["policy_root"] = str(repo_root)
    # Load .env from repo root when using a live LLM backend so OPENAI_API_KEY etc. are available
    if llm_backend in (
        "openai_live",
        "openai_responses",
        "anthropic_live",
        "ollama_live",
        "openai_hosted",
    ):
        try:
            from dotenv import load_dotenv

            env_path = repo_root / ".env"
            if env_path.is_file():
                load_dotenv(env_path)
        except ImportError:
            pass
    # Fail-fast when a live backend requiring an API key is selected but the key is missing
    from labtrust_gym.baselines.llm.credentials import require_credentials_for_backend

    require_credentials_for_backend(llm_backend, repo_root)
    effective_policy: dict[str, Any] | None = None
    policy_fingerprint: str | None = None
    if domain_id:
        from labtrust_gym.policy.loader import load_policy_for_domain

        try:
            effective_policy, policy_fingerprint, _, _, domain_overrides = load_policy_for_domain(
                repo_root, domain_id=domain_id, partner_id=partner_id
            )
            if domain_overrides and effective_policy is not None:
                for key, val in domain_overrides.items():
                    if isinstance(val, dict) and isinstance(effective_policy.get(key), dict):
                        effective_policy = dict(effective_policy)
                        effective_policy[key] = {**(effective_policy[key] or {}), **val}
                    else:
                        effective_policy = dict(effective_policy) if effective_policy else {}
                        effective_policy[key] = val
            if effective_policy is not None:
                overrides = overrides or {}
                overrides["effective_policy"] = effective_policy
        except Exception as e:
            raise RuntimeError(f"Failed to load policy for domain {domain_id!r}: {e}") from e
    elif partner_id:
        from labtrust_gym.policy.loader import load_effective_policy

        try:
            effective_policy, policy_fingerprint, _, _ = load_effective_policy(repo_root, partner_id=partner_id)
        except Exception as e:
            raise RuntimeError(f"Failed to load partner overlay {partner_id!r}: {e}") from e
    if (partner_id or domain_id) and effective_policy is not None and effective_policy.get("calibration"):
        overrides["calibration"] = effective_policy["calibration"]
    use_strict_signatures = bool(
        task.get_initial_state(0, policy_root=repo_root).get("strict_signatures")
        or (overrides or {}).get("strict_signatures")
    )
    # Inject tool registry so engine can gate tool_id calls (B010).
    try:
        from labtrust_gym.tools.registry import (
            load_tool_registry,
        )
        from labtrust_gym.tools.registry import (
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
            except Exception as e:
                _LOG.warning("Failed to load state_tool_capability_map, skipping: %s", e)
            try:
                from labtrust_gym.auth.authorize import rbac_policy_fingerprint
                from labtrust_gym.engine.rbac import load_rbac_policy

                rbac_path = repo_root / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
                rbac_policy = load_rbac_policy(rbac_path)
                if rbac_policy and rbac_policy.get("roles"):
                    overrides["rbac_policy_fingerprint"] = rbac_policy_fingerprint(rbac_policy)
            except Exception as e:
                _LOG.warning("Failed to load rbac_policy_fingerprint, skipping: %s", e)
    except Exception as e:
        _LOG.warning("Failed to load tool_registry / tool_registry_fingerprint, skipping: %s", e)
    key_registry_merged: dict[str, Any] | None = None
    get_private_key_fn: Any | None = None
    if llm_backend and use_strict_signatures:
        from labtrust_gym.baselines.llm.signing_proxy import (
            ensure_run_ephemeral_key,
        )
        from labtrust_gym.engine.signatures import load_key_registry

        key_path = repo_root / "policy" / "keys" / "key_registry.v0.1.yaml"
        key_registry_base = load_key_registry(key_path) if key_path.exists() else {"version": "0.1", "keys": []}
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
    is_scale_task = task_name in ("coord_scale", "coord_risk")
    scale_probe_state: dict[str, Any] | None = None
    coord_method_instance: Any | None = None
    coord_records: dict[str, str] = {}
    coord_method_for_branch: str | None = None
    if is_scale_task:
        coord_method_for_branch = coord_method or ""
        if scale_config_override is not None:
            from labtrust_gym.benchmarks.coordination_scale import (
                generate_scaled_initial_state,
            )

            scale_probe_state = generate_scaled_initial_state(scale_config_override, repo_root, base_seed)
            task.max_steps = scale_config_override.horizon_steps
            task.scale_config = scale_config_override
        else:
            scale_probe_state = task.get_initial_state(base_seed, policy_root=repo_root)
    if is_scale_task and coord_method:
        from dataclasses import asdict

        from labtrust_gym.baselines.coordination.registry import (
            make_coordination_method,
        )

        _scale_cfg = scale_config_override if scale_config_override is not None else getattr(task, "scale_config", None)
        scale_config_dict = (
            asdict(scale_config_override)
            if scale_config_override is not None
            else (asdict(_scale_cfg) if _scale_cfg is not None else {})
        )
        if task_name == "coord_risk" and injection_id:
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict["injection_id"] = injection_id
        if (overrides or {}).get("model_path") and coord_method and "marl_ppo" in str(coord_method):
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict["model_path"] = overrides["model_path"]
        policy_for_coord = (scale_probe_state or {}).get("effective_policy") or {}
        # Resolve variant to base for backend branch (e.g. llm_central_planner_shielded -> llm_central_planner)
        coord_method_for_branch = coord_method
        if repo_root:
            try:
                from labtrust_gym.policy.coordination import (
                    load_coordination_methods,
                    resolve_method_variant,
                )

                reg_path = repo_root / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
                if reg_path.exists():
                    _reg = load_coordination_methods(reg_path)
                    base_id, _ = resolve_method_variant(coord_method, _reg)
                    if base_id != coord_method:
                        coord_method_for_branch = base_id
            except Exception as e:
                _LOG.warning("Failed to resolve coordination method variant, using method as-is: %s", e)
        if coord_method == "llm_constrained":
            from labtrust_gym.baselines.llm.agent import (
                DeterministicConstrainedBackend,
                LLMAgentWithShield,
            )
            from labtrust_gym.engine.rbac import load_rbac_policy
            from labtrust_gym.security.agent_capabilities import load_agent_capabilities

            scale_agents = (scale_probe_state or {}).get("agents") or []
            pz_to_engine_scale = {
                f"worker_{i}": scale_agents[i]["agent_id"] for i in range(len(scale_agents)) if i < len(scale_agents)
            }
            rbac_path = repo_root / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
            rbac_policy = load_rbac_policy(rbac_path)
            capability_policy = load_agent_capabilities(repo_root)
            constrained_backend = None
            if llm_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_live import (
                    OpenAILiveBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(llm_backend, repo_root)
                constrained_backend = OpenAILiveBackend(
                    **creds,
                    model=llm_model,
                )
                llm_backend_ref = constrained_backend
            elif llm_backend == "ollama_live":
                from labtrust_gym.baselines.llm.backends.ollama_live import (
                    OllamaLiveBackend,
                )

                constrained_backend = OllamaLiveBackend(model=llm_model)
                llm_backend_ref = constrained_backend
            elif llm_backend == "anthropic_live":
                from labtrust_gym.baselines.llm.backends.anthropic_live import (
                    AnthropicLiveBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(llm_backend, repo_root)
                constrained_backend = AnthropicLiveBackend(**creds, model=llm_model)
                llm_backend_ref = constrained_backend
            if constrained_backend is None:
                constrained_backend = DeterministicConstrainedBackend(seed=base_seed, default_action_type="NOOP")
            llm_agent = LLMAgentWithShield(
                backend=constrained_backend,
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
            n_max = int(scale_config_dict.get("coord_propose_actions_max_agents", 50))
            if len(pz_to_engine_scale) > n_max and scripted_agents_map is not None:
                try:
                    from labtrust_gym.online.rate_limit import TokenBucket
                except ImportError:
                    TokenBucket = None
                global_rl = TokenBucket(rate=10.0, capacity=20.0) if TokenBucket else None
                shared_cb = None
                if scale_config_dict.get("shared_circuit_breaker_per_backend"):
                    from labtrust_gym.baselines.llm.throttle import (
                        CircuitBreaker,
                        throttle_config_from_env,
                    )

                    _cb_cfg = throttle_config_from_env()
                    shared_cb = CircuitBreaker(
                        consecutive_threshold=int(_cb_cfg.get("circuit_consecutive_threshold", 5)),
                        cooldown_calls=int(_cb_cfg.get("circuit_cooldown_calls", 10)),
                    )
                max_wait_s = scale_config_dict.get("global_rate_limit_max_wait_s")
                for aid in pz_to_engine_scale:
                    scripted_agents_map[aid] = LLMAgentWithShield(
                        backend=constrained_backend,
                        rbac_policy=rbac_policy,
                        pz_to_engine=pz_to_engine_scale,
                        strict_signatures=use_strict_signatures,
                        key_registry=key_registry_merged or {},
                        get_private_key=get_private_key_fn or (lambda _: None),
                        capability_policy=capability_policy,
                        global_rate_limiter=global_rl,
                        circuit_breaker=shared_cb,
                        global_rate_limit_max_wait_s=max_wait_s,
                    )
        elif coord_method_for_branch == "llm_central_planner":
            scale_agents = (scale_probe_state or {}).get("agents") or []
            pz_to_engine_central = {
                f"worker_{i}": scale_agents[i]["agent_id"] for i in range(len(scale_agents)) if i < len(scale_agents)
            }
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict.setdefault("seed", base_seed)
            policy_for_coord = (policy_for_coord or {}).copy()
            policy_for_coord.setdefault("pz_to_engine", pz_to_engine_central)
            planner_backend = (
                coord_planner_backend if (coord_planner_backend and coord_planner_backend != "inherit") else llm_backend
            )
            planner_model = (
                coord_planner_model if (coord_planner_model and coord_planner_model != "inherit") else llm_model
            )
            proposal_backend = None
            if coord_proposal_backend_override is not None:
                proposal_backend = coord_proposal_backend_override
                llm_backend_ref = coord_proposal_backend_override
            elif planner_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
                    OpenAICoordinationProposalBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(planner_backend, repo_root)
                proposal_backend = OpenAICoordinationProposalBackend(
                    **creds,
                    model=planner_model,
                    repo_root=repo_root,
                )
                llm_backend_ref = proposal_backend
            elif planner_backend == "ollama_live":
                from labtrust_gym.baselines.llm.backends.ollama_coordination_backend import (
                    OllamaCoordinationProposalBackend,
                )

                proposal_backend = OllamaCoordinationProposalBackend(
                    model=planner_model,
                )
                llm_backend_ref = proposal_backend
            elif planner_backend == "anthropic_live":
                from labtrust_gym.baselines.llm.backends.anthropic_live import (
                    AnthropicCoordinationProposalBackend,
                )

                proposal_backend = AnthropicCoordinationProposalBackend(
                    model=planner_model,
                    repo_root=repo_root,
                )
                llm_backend_ref = proposal_backend
            if proposal_backend is None and repo_root is not None:
                if coord_fixtures_path is not None:
                    from labtrust_gym.baselines.llm.record_fixtures_coord import (
                        FixtureProposalBackend,
                    )

                    proposal_backend = FixtureProposalBackend(
                        coord_fixtures_path,
                        "llm_central_planner",
                    )
                else:
                    from labtrust_gym.baselines.coordination.methods.llm_central_planner import (
                        DeterministicProposalBackend,
                    )

                    seed = int(scale_config_dict.get("seed", base_seed))
                    proposal_backend = DeterministicProposalBackend(
                        seed=seed,
                        default_action_type="NOOP",
                    )
            if proposal_backend is None:
                raise ValueError(
                    "llm_central_planner requires proposal_backend= or repo_root for deterministic backend"
                )
            if pipeline_mode == "llm_offline" and repo_root is not None:
                from labtrust_gym.baselines.llm.fault_model import load_llm_fault_model
                from labtrust_gym.baselines.llm.fault_model_coord import (
                    LLMFaultModelCoordWrapper,
                )

                coord_fault_cfg = load_llm_fault_model(repo_root)
                if coord_fault_cfg:
                    seed = int(scale_config_dict.get("seed", base_seed))
                    proposal_backend = LLMFaultModelCoordWrapper(
                        proposal_backend,
                        coord_fault_cfg,
                        seed=seed,
                        method_id="llm_central_planner",
                    )
            if record_coord_fixtures_path is not None:
                from labtrust_gym.baselines.llm.record_fixtures_coord import (
                    RecordingProposalBackend,
                )

                proposal_backend = RecordingProposalBackend(
                    proposal_backend,
                    "llm_central_planner",
                    coord_records,
                )
            if pipeline_mode == "llm_live":
                from labtrust_gym.baselines.llm.coordinator_throttle import (
                    CoordinatorGuardrailProposalBackend,
                )

                proposal_backend = CoordinatorGuardrailProposalBackend(proposal_backend)
            coord_method_instance = make_coordination_method(
                coord_method,
                policy_for_coord,
                repo_root=repo_root,
                scale_config=scale_config_dict,
                pz_to_engine=pz_to_engine_central,
                proposal_backend=proposal_backend,
            )
        elif coord_method_for_branch == "llm_hierarchical_allocator":
            scale_agents = (scale_probe_state or {}).get("agents") or []
            pz_to_engine_hier = {
                f"worker_{i}": scale_agents[i]["agent_id"] for i in range(len(scale_agents)) if i < len(scale_agents)
            }
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict.setdefault("seed", base_seed)
            policy_for_coord = (policy_for_coord or {}).copy()
            policy_for_coord.setdefault("pz_to_engine", pz_to_engine_hier)
            alloc_planner_backend = (
                coord_planner_backend if (coord_planner_backend and coord_planner_backend != "inherit") else llm_backend
            )
            alloc_planner_model = (
                coord_planner_model if (coord_planner_model and coord_planner_model != "inherit") else llm_model
            )
            allocator_backend = None
            if alloc_planner_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
                    OpenAICoordinationProposalBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(llm_backend, repo_root)
                allocator_backend = OpenAICoordinationProposalBackend(
                    **creds,
                    model=alloc_planner_model,
                    repo_root=repo_root,
                )
                llm_backend_ref = allocator_backend
            elif alloc_planner_backend == "ollama_live":
                from labtrust_gym.baselines.llm.backends.ollama_coordination_backend import (
                    OllamaCoordinationProposalBackend,
                )

                allocator_backend = OllamaCoordinationProposalBackend(
                    model=alloc_planner_model,
                )
                llm_backend_ref = allocator_backend
            elif alloc_planner_backend == "anthropic_live":
                from labtrust_gym.baselines.llm.backends.anthropic_live import (
                    AnthropicCoordinationProposalBackend,
                )

                allocator_backend = AnthropicCoordinationProposalBackend(
                    model=alloc_planner_model,
                    repo_root=repo_root,
                )
                llm_backend_ref = allocator_backend
            if allocator_backend is None and repo_root is not None:
                from labtrust_gym.baselines.coordination.methods.llm_hierarchical_allocator import (
                    DeterministicAssignmentsBackend,
                )

                seed = int(scale_config_dict.get("seed", base_seed))
                allocator_backend = DeterministicAssignmentsBackend(seed=seed)
            if allocator_backend is None:
                raise ValueError(
                    "llm_hierarchical_allocator requires allocator_backend= or repo_root for deterministic backend"
                )
            if pipeline_mode == "llm_live":
                from labtrust_gym.baselines.llm.coordinator_throttle import (
                    CoordinatorGuardrailProposalBackend,
                )

                allocator_backend = CoordinatorGuardrailProposalBackend(allocator_backend)
            coord_method_instance = make_coordination_method(
                coord_method,
                policy_for_coord,
                repo_root=repo_root,
                scale_config=scale_config_dict,
                pz_to_engine=pz_to_engine_hier,
                allocator_backend=allocator_backend,
            )
        elif coord_method_for_branch == "llm_auction_bidder":
            scale_agents = (scale_probe_state or {}).get("agents") or []
            pz_to_engine_auc = {
                f"worker_{i}": scale_agents[i]["agent_id"] for i in range(len(scale_agents)) if i < len(scale_agents)
            }
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict.setdefault("seed", base_seed)
            if task_name == "coord_risk" and injection_id:
                scale_config_dict["injection_id"] = injection_id
            policy_for_coord = (policy_for_coord or {}).copy()
            policy_for_coord.setdefault("pz_to_engine", pz_to_engine_auc)
            bidder_backend = (
                coord_bidder_backend if (coord_bidder_backend and coord_bidder_backend != "inherit") else llm_backend
            )
            bidder_model = coord_bidder_model if (coord_bidder_model and coord_bidder_model != "inherit") else llm_model
            bid_backend = None
            if bidder_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_bid_backend import (
                    OpenAIBidBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(bidder_backend, repo_root)
                bid_backend = OpenAIBidBackend(
                    **creds,
                    model=bidder_model,
                    repo_root=repo_root,
                )
                llm_backend_ref = bid_backend
            elif bidder_backend == "ollama_live":
                from labtrust_gym.baselines.llm.backends.ollama_coordination_backend import (
                    OllamaBidBackend,
                )

                bid_backend = OllamaBidBackend(model=bidder_model)
                llm_backend_ref = bid_backend
            elif bidder_backend == "anthropic_live":
                from labtrust_gym.baselines.llm.backends.anthropic_live import (
                    AnthropicBidBackend,
                )

                bid_backend = AnthropicBidBackend(model=bidder_model, repo_root=repo_root)
                llm_backend_ref = bid_backend
            if bid_backend is None and repo_root is not None:
                if coord_fixtures_path is not None:
                    from labtrust_gym.baselines.llm.record_fixtures_coord import (
                        FixtureProposalBackend,
                    )

                    bid_backend = FixtureProposalBackend(
                        coord_fixtures_path,
                        "llm_auction_bidder",
                    )
                else:
                    from labtrust_gym.baselines.coordination.methods.llm_auction_bidder import (
                        DeterministicBidBackend,
                    )

                    seed = int(scale_config_dict.get("seed", base_seed))
                    bid_backend = DeterministicBidBackend(seed=seed)
            if bid_backend is None:
                raise ValueError("llm_auction_bidder requires bid_backend= or repo_root for deterministic backend")
            if pipeline_mode == "llm_offline" and repo_root is not None:
                from labtrust_gym.baselines.llm.fault_model import load_llm_fault_model
                from labtrust_gym.baselines.llm.fault_model_coord import (
                    LLMFaultModelCoordWrapper,
                )

                coord_fault_cfg = load_llm_fault_model(repo_root)
                if coord_fault_cfg:
                    seed = int(scale_config_dict.get("seed", base_seed))
                    bid_backend = LLMFaultModelCoordWrapper(
                        bid_backend,
                        coord_fault_cfg,
                        seed=seed,
                        method_id="llm_auction_bidder",
                    )
            if record_coord_fixtures_path is not None:
                from labtrust_gym.baselines.llm.record_fixtures_coord import (
                    RecordingProposalBackend,
                )

                bid_backend = RecordingProposalBackend(
                    bid_backend,
                    "llm_auction_bidder",
                    coord_records,
                )
            if pipeline_mode == "llm_live":
                from labtrust_gym.baselines.llm.coordinator_throttle import (
                    CoordinatorGuardrailBidBackend,
                )

                bid_backend = CoordinatorGuardrailBidBackend(bid_backend)
            coord_method_instance = make_coordination_method(
                coord_method,
                policy_for_coord,
                repo_root=repo_root,
                scale_config=scale_config_dict,
                bid_backend=bid_backend,
            )
        elif coord_method_for_branch == "llm_gossip_summarizer":
            scale_agents = (scale_probe_state or {}).get("agents") or []
            pz_to_engine_gossip = {
                f"worker_{i}": scale_agents[i]["agent_id"] for i in range(len(scale_agents)) if i < len(scale_agents)
            }
            if not pz_to_engine_gossip:
                pz_to_engine_gossip = {"worker_0": "ops_0", "worker_1": "runner_0"}
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict.setdefault("seed", base_seed)
            if task_name == "coord_risk" and injection_id:
                scale_config_dict["injection_id"] = injection_id
            policy_for_coord = (policy_for_coord or {}).copy()
            policy_for_coord.setdefault("pz_to_engine", pz_to_engine_gossip)
            summary_backend_gossip = None
            if llm_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
                    OpenAIGossipSummaryBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(llm_backend, repo_root)
                summary_backend_gossip = OpenAIGossipSummaryBackend(
                    **creds,
                    model=llm_model,
                    repo_root=repo_root,
                )
                llm_backend_ref = summary_backend_gossip._backend
            elif llm_backend == "ollama_live":
                from labtrust_gym.baselines.llm.backends.ollama_coordination_backend import (
                    OllamaGossipSummaryBackend,
                )

                summary_backend_gossip = OllamaGossipSummaryBackend(model=llm_model)
                llm_backend_ref = summary_backend_gossip
            coord_method_instance = make_coordination_method(
                coord_method,
                policy_for_coord,
                repo_root=repo_root,
                scale_config=scale_config_dict,
                pz_to_engine=pz_to_engine_gossip,
                summary_backend=summary_backend_gossip,
            )
        elif coord_method == "llm_local_decider_signed_bus":
            scale_agents = (scale_probe_state or {}).get("agents") or []
            pz_to_engine_local = {
                f"worker_{i}": scale_agents[i]["agent_id"] for i in range(len(scale_agents)) if i < len(scale_agents)
            }
            if not pz_to_engine_local:
                pz_to_engine_local = {"worker_0": "ops_0", "worker_1": "runner_0"}
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict.setdefault("seed", base_seed)
            if task_name == "coord_risk" and injection_id:
                scale_config_dict["injection_id"] = injection_id
            policy_for_coord = (policy_for_coord or {}).copy()
            policy_for_coord.setdefault("pz_to_engine", pz_to_engine_local)
            local_proposal_backend = None
            if llm_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
                    OpenAILocalProposalBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(llm_backend, repo_root)
                local_proposal_backend = OpenAILocalProposalBackend(
                    **creds,
                    model=llm_model,
                    repo_root=repo_root,
                )
                llm_backend_ref = local_proposal_backend
            elif llm_backend == "ollama_live":
                from labtrust_gym.baselines.llm.backends.ollama_coordination_backend import (
                    OllamaLocalProposalBackend,
                )

                local_proposal_backend = OllamaLocalProposalBackend(model=llm_model)
                llm_backend_ref = local_proposal_backend
            coord_method_instance = make_coordination_method(
                coord_method,
                policy_for_coord,
                repo_root=repo_root,
                scale_config=scale_config_dict,
                pz_to_engine=pz_to_engine_local,
                proposal_backend=local_proposal_backend,
            )
        elif coord_method == "llm_repair_over_kernel_whca":
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict.setdefault("seed", base_seed)
            if task_name == "coord_risk" and injection_id:
                scale_config_dict["injection_id"] = injection_id
            if pipeline_mode == "llm_offline" and repo_root is not None:
                from labtrust_gym.baselines.llm.fault_model import (
                    load_llm_fault_model,
                )

                fault_model_config = load_llm_fault_model(repo_root)
                if fault_model_config:
                    scale_config_dict["fault_model_config"] = fault_model_config
            repair_role_backend = (
                coord_repair_backend if (coord_repair_backend and coord_repair_backend != "inherit") else llm_backend
            )
            repair_role_model = (
                coord_repair_model if (coord_repair_model and coord_repair_model != "inherit") else llm_model
            )
            repair_backend_param = None
            if repair_role_backend == "openai_live":
                from labtrust_gym.baselines.coordination.methods.llm_repair_over_kernel_whca import (
                    LiveRepairBackend,
                )
                from labtrust_gym.baselines.llm.backends.openai_live import (
                    OpenAILiveBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(repair_role_backend, repo_root)
                repair_backend_param = LiveRepairBackend(OpenAILiveBackend(**creds, model=repair_role_model))
                llm_backend_ref = repair_backend_param._backend
            elif repair_role_backend == "ollama_live":
                from labtrust_gym.baselines.coordination.methods.llm_repair_over_kernel_whca import (
                    LiveRepairBackend,
                )
                from labtrust_gym.baselines.llm.backends.ollama_live import (
                    OllamaLiveBackend,
                )

                repair_backend_param = LiveRepairBackend(OllamaLiveBackend(model=repair_role_model))
                llm_backend_ref = repair_backend_param._backend
            elif repair_role_backend == "anthropic_live":
                from labtrust_gym.baselines.coordination.methods.llm_repair_over_kernel_whca import (
                    LiveRepairBackend,
                )
                from labtrust_gym.baselines.llm.backends.anthropic_live import (
                    AnthropicLiveBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(repair_role_backend, repo_root)
                repair_backend_param = LiveRepairBackend(AnthropicLiveBackend(**creds, model=repair_role_model))
                llm_backend_ref = repair_backend_param._backend
            if pipeline_mode == "llm_live" and repair_backend_param is not None:
                from labtrust_gym.baselines.llm.coordinator_throttle import (
                    CoordinatorGuardrailRepairBackend,
                )

                repair_backend_param = CoordinatorGuardrailRepairBackend(repair_backend_param)
            coord_method_instance = make_coordination_method(
                coord_method,
                policy_for_coord,
                repo_root=repo_root,
                scale_config=scale_config_dict,
                repair_backend=repair_backend_param,
            )
        elif coord_method == "llm_detector_throttle_advisor":
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict.setdefault("seed", base_seed)
            detector_role_backend = (
                coord_detector_backend
                if (coord_detector_backend and coord_detector_backend != "inherit")
                else llm_backend
            )
            detector_role_model = (
                coord_detector_model if (coord_detector_model and coord_detector_model != "inherit") else llm_model
            )
            if detector_role_backend == "openai_live":
                from labtrust_gym.baselines.coordination.assurance import (
                    LiveDetectorBackend,
                )
                from labtrust_gym.baselines.llm.backends.openai_live import (
                    OpenAILiveBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(detector_role_backend, repo_root)
                live_backend = OpenAILiveBackend(**creds, model=detector_role_model)
                scale_config_dict["detector_backend"] = LiveDetectorBackend(live_backend)
                llm_backend_ref = live_backend
            elif detector_role_backend == "ollama_live":
                from labtrust_gym.baselines.coordination.assurance import (
                    LiveDetectorBackend,
                )
                from labtrust_gym.baselines.llm.backends.ollama_live import (
                    OllamaLiveBackend,
                )

                live_backend = OllamaLiveBackend(model=detector_role_model)
                scale_config_dict["detector_backend"] = LiveDetectorBackend(live_backend)
                llm_backend_ref = live_backend
            elif detector_role_backend == "anthropic_live":
                from labtrust_gym.baselines.coordination.assurance import (
                    LiveDetectorBackend,
                )
                from labtrust_gym.baselines.llm.backends.anthropic_live import (
                    AnthropicLiveBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(detector_role_backend, repo_root)
                live_backend = AnthropicLiveBackend(**creds, model=detector_role_model)
                scale_config_dict["detector_backend"] = LiveDetectorBackend(live_backend)
                llm_backend_ref = live_backend
            if pipeline_mode == "llm_live" and scale_config_dict.get("detector_backend") is not None:
                from labtrust_gym.baselines.llm.coordinator_throttle import (
                    CoordinatorGuardrailDetectorBackend,
                )

                scale_config_dict["detector_backend"] = CoordinatorGuardrailDetectorBackend(
                    scale_config_dict["detector_backend"]
                )
            coord_method_instance = make_coordination_method(
                coord_method,
                policy_for_coord,
                repo_root=repo_root,
                scale_config=scale_config_dict,
            )
        elif coord_method_for_branch == "llm_central_planner_debate":
            scale_agents = (scale_probe_state or {}).get("agents") or []
            pz_to_engine_central = {
                f"worker_{i}": scale_agents[i]["agent_id"] for i in range(len(scale_agents)) if i < len(scale_agents)
            }
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict.setdefault("seed", base_seed)
            policy_for_coord = (policy_for_coord or {}).copy()
            policy_for_coord.setdefault("pz_to_engine", pz_to_engine_central)
            planner_backend = (
                coord_planner_backend if (coord_planner_backend and coord_planner_backend != "inherit") else llm_backend
            )
            planner_model = (
                coord_planner_model if (coord_planner_model and coord_planner_model != "inherit") else llm_model
            )
            n_proposers = int(scale_config_dict.get("coord_debate_proposers", 2))
            n_proposers = max(1, min(n_proposers, 5))
            proposal_backends_list: list[Any] = []
            if planner_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
                    OpenAICoordinationProposalBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(planner_backend, repo_root)
                for _ in range(n_proposers):
                    proposal_backends_list.append(
                        OpenAICoordinationProposalBackend(
                            **creds,
                            model=planner_model,
                            repo_root=repo_root,
                        )
                    )
                llm_backend_ref = proposal_backends_list[0] if proposal_backends_list else None
            elif planner_backend == "ollama_live":
                from labtrust_gym.baselines.llm.backends.ollama_coordination_backend import (
                    OllamaCoordinationProposalBackend,
                )

                for _ in range(n_proposers):
                    proposal_backends_list.append(OllamaCoordinationProposalBackend(model=planner_model))
                llm_backend_ref = proposal_backends_list[0] if proposal_backends_list else None
            elif planner_backend == "anthropic_live":
                from labtrust_gym.baselines.llm.backends.anthropic_live import (
                    AnthropicCoordinationProposalBackend,
                )

                for _ in range(n_proposers):
                    proposal_backends_list.append(
                        AnthropicCoordinationProposalBackend(
                            model=planner_model,
                            repo_root=repo_root,
                        )
                    )
                llm_backend_ref = proposal_backends_list[0] if proposal_backends_list else None
            if proposal_backends_list:
                if pipeline_mode == "llm_live":
                    from labtrust_gym.baselines.llm.coordinator_throttle import (
                        CoordinatorGuardrailProposalBackend,
                    )

                    proposal_backends_list = [CoordinatorGuardrailProposalBackend(b) for b in proposal_backends_list]
                coord_method_instance = make_coordination_method(
                    coord_method,
                    policy_for_coord,
                    repo_root=repo_root,
                    scale_config=scale_config_dict,
                    pz_to_engine=pz_to_engine_central,
                    proposal_backend=proposal_backends_list,
                )
            else:
                coord_method_instance = make_coordination_method(
                    coord_method,
                    policy_for_coord,
                    repo_root=repo_root,
                    scale_config=scale_config_dict,
                    pz_to_engine=pz_to_engine_central,
                )
        elif coord_method_for_branch == "llm_central_planner_agentic":
            scale_agents = (scale_probe_state or {}).get("agents") or []
            pz_to_engine_central = {
                f"worker_{i}": scale_agents[i]["agent_id"] for i in range(len(scale_agents)) if i < len(scale_agents)
            }
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict.setdefault("seed", base_seed)
            policy_for_coord = (policy_for_coord or {}).copy()
            policy_for_coord.setdefault("pz_to_engine", pz_to_engine_central)
            planner_backend = (
                coord_planner_backend if (coord_planner_backend and coord_planner_backend != "inherit") else llm_backend
            )
            planner_model = (
                coord_planner_model if (coord_planner_model and coord_planner_model != "inherit") else llm_model
            )
            agentic_proposal_backend: Any = None
            if planner_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_agentic_coord_backend import (
                    OpenAIAgenticProposalBackend,
                )
                from labtrust_gym.baselines.llm.credentials import resolve_credentials

                creds = resolve_credentials(planner_backend, repo_root)
                agentic_proposal_backend = OpenAIAgenticProposalBackend(
                    **creds,
                    model=planner_model,
                    repo_root=repo_root,
                )
                llm_backend_ref = agentic_proposal_backend
            if agentic_proposal_backend is not None:
                if pipeline_mode == "llm_live":
                    from labtrust_gym.baselines.llm.coordinator_throttle import (
                        CoordinatorGuardrailProposalBackend,
                    )

                    agentic_proposal_backend = CoordinatorGuardrailProposalBackend(agentic_proposal_backend)
                coord_method_instance = make_coordination_method(
                    coord_method,
                    policy_for_coord,
                    repo_root=repo_root,
                    scale_config=scale_config_dict,
                    pz_to_engine=pz_to_engine_central,
                    proposal_backend=agentic_proposal_backend,
                )
            else:
                coord_method_instance = make_coordination_method(
                    coord_method,
                    policy_for_coord,
                    repo_root=repo_root,
                    scale_config=scale_config_dict,
                    pz_to_engine=pz_to_engine_central,
                )
        else:
            coord_method_instance = make_coordination_method(
                coord_method,
                policy_for_coord,
                repo_root=repo_root,
                scale_config=scale_config_dict,
                model_path=scale_config_dict.get("model_path"),
            )

    if task_name == "coord_risk" and injection_id == "INJ-ID-SPOOF-001":
        overrides["strict_signatures"] = True
    risk_injector_instance: Any | None = None
    if task_name == "coord_risk" and injection_id:
        if injection_id == "INJ-BID-SPOOF-001":
            pass
        else:
            from labtrust_gym.policy.coordination import load_coordination_study_spec
            from labtrust_gym.security.risk_injections import make_injector

            spec_path = repo_root / "policy" / "coordination" / "coordination_study_spec.v0.1.yaml"
            intensity = 0.2
            seed_offset = 0
            application_phase: str | None = None
            early_step_cap_spec: int | None = None
            late_step_min_spec: int | None = None
            if spec_path.exists():
                try:
                    spec = load_coordination_study_spec(spec_path)
                    for inj in spec.get("injections") or []:
                        if isinstance(inj, dict) and inj.get("injection_id") == injection_id:
                            intensity = float(inj.get("intensity", 0.2))
                            seed_offset = int(inj.get("seed_offset", 0))
                            application_phase = inj.get("application_phase") or None
                            ec = inj.get("early_step_cap")
                            early_step_cap_spec = int(ec) if ec is not None else None
                            lm = inj.get("late_step_min")
                            late_step_min_spec = int(lm) if lm is not None else None
                            break
                except Exception as e:
                    _LOG.warning("Failed to load injection spec from coordination_study_spec, using fallback: %s", e)
            # Fallback: load application_phase / step bounds from injections.v0.2.yaml
            if (application_phase is None or early_step_cap_spec is None or late_step_min_spec is None) and repo_root:
                inj_policy_path = repo_root / "policy" / "coordination" / "injections.v0.2.yaml"
                if inj_policy_path.is_file():
                    try:
                        from labtrust_gym.policy.loader import load_yaml

                        inj_data = load_yaml(inj_policy_path)
                        for inj in inj_data.get("injections") or []:
                            if isinstance(inj, dict) and inj.get("injection_id") == injection_id:
                                if application_phase is None:
                                    application_phase = inj.get("application_phase") or None
                                if early_step_cap_spec is None:
                                    ec = inj.get("early_step_cap")
                                    early_step_cap_spec = int(ec) if ec is not None else None
                                if late_step_min_spec is None:
                                    lm = inj.get("late_step_min")
                                    late_step_min_spec = int(lm) if lm is not None else None
                                break
                    except Exception as e:
                        _LOG.warning("Failed to load injection policy for step bounds: %s", e)
            phase = injection_phase if injection_phase is not None else application_phase
            risk_injector_instance = make_injector(
                injection_id,
                intensity=intensity,
                seed_offset=seed_offset,
                application_phase=phase,
                early_step_cap=early_step_cap if early_step_cap is not None else early_step_cap_spec,
                late_step_min=late_step_min if late_step_min is not None else late_step_min_spec,
            )

    if env_factory is None:
        from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

        num_adversaries = 1 if task_name == "adversarial_disruption" else 0
        num_insiders = 1 if task_name == "insider_key_misuse" else 0
        num_runners = 1 if num_insiders else 2

        policy_dir = repo_root / "policy"

        # Resolve domain adapter: use domain registry when domain_id set, else default hospital_lab
        _domain_id = domain_id if domain_id else "hospital_lab"
        from labtrust_gym.domain import get_domain_adapter_factory

        _adapter_factory_fn = get_domain_adapter_factory(_domain_id)
        if _adapter_factory_fn is None:
            from labtrust_gym.domain.lab_adapter import lab_domain_adapter_factory

            _adapter_factory_fn = lab_domain_adapter_factory
        _adapter_factory_fn_ref = _adapter_factory_fn

        def _engine_factory() -> Any:
            return _adapter_factory_fn_ref({}, None)

        if is_scale_task and scale_probe_state:
            scale_agents = scale_probe_state.get("agents") or []
            scale_device_ids = scale_probe_state.get("_scale_device_ids")
            scale_zone_ids = scale_probe_state.get("_scale_zone_ids")

            def _env_factory(
                initial_state: dict[str, Any],
                reward_config: dict[str, Any],
                log_path: Path | None = None,
                policy_fingerprint: str | None = None,
                partner_id: str | None = None,
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
                    engine_factory=_engine_factory,
                )

        else:

            def _env_factory(
                initial_state: dict[str, Any],
                reward_config: dict[str, Any],
                log_path: Path | None = None,
                policy_fingerprint: str | None = None,
                partner_id: str | None = None,
            ) -> Any:
                return LabTrustParallelEnv(
                    num_runners=num_runners,
                    num_adversaries=num_adversaries,
                    num_insiders=num_insiders,
                    dt_s=10,
                    reward_config=reward_config,
                    policy_dir=policy_dir,
                    log_path=log_path,
                    engine_factory=_engine_factory,
                )

        def _make_env(
            initial_state: dict[str, Any],
            reward_config: dict[str, Any],
            log_path: Path | None = None,
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
            DEFAULT_DEVICE_IDS,
            DEFAULT_ZONE_IDS,
        )

        if is_scale_task and scale_probe_state:
            scale_agents = scale_probe_state.get("agents") or []
            scale_device_ids = scale_probe_state.get("_scale_device_ids") or DEFAULT_DEVICE_IDS
            scale_zone_ids = scale_probe_state.get("_scale_zone_ids") or DEFAULT_ZONE_IDS
            scripted_agents_map = {
                f"worker_{i}": ScriptedRunnerAgent(
                    zone_ids=scale_zone_ids,
                    device_ids=scale_device_ids,
                )
                for i in range(len(scale_agents))
            }
        else:
            from labtrust_gym.baselines.scripted_qc import ScriptedQcAgent
            from labtrust_gym.baselines.scripted_supervisor import (
                ScriptedSupervisorAgent,
            )

            num_insiders = 1 if task_name == "insider_key_misuse" else 0
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
                "qc_0": ScriptedQcAgent(),
                "supervisor_0": ScriptedSupervisorAgent(),
            }
        rbac_policy_llm: dict[str, Any] | None = None
        capability_policy_llm: dict[str, Any] | None = None
        if not is_scale_task and llm_backend is not None:
            from labtrust_gym.engine.rbac import load_rbac_policy
            from labtrust_gym.security.agent_capabilities import load_agent_capabilities

            rbac_path_llm = (repo_root or Path.cwd()) / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
            rbac_policy_llm = load_rbac_policy(rbac_path_llm)
            capability_policy_llm = load_agent_capabilities(repo_root or Path.cwd())
        if not is_scale_task and llm_backend == "deterministic":
            from labtrust_gym.baselines.llm.agent import (
                FixtureBackend,
                LLMAgentWithShield,
            )

            pz_to_engine = _default_pz_to_engine(num_runners=num_runners, num_insiders=num_insiders)
            backend = FixtureBackend(repo_root=repo_root)
            if pipeline_mode == "llm_offline" and repo_root is not None:
                from labtrust_gym.baselines.llm.fault_model import load_llm_fault_model
                from labtrust_gym.baselines.llm.fault_model_agent import (
                    LLMFaultModelAgentWrapper,
                )

                fault_cfg = load_llm_fault_model(repo_root)
                if fault_cfg:
                    backend = LLMFaultModelAgentWrapper(backend, fault_cfg, base_seed)
            llm_backend_ref = cast(Any, backend)
            for aid in llm_agents:
                if aid not in scripted_agents_map:
                    continue
                scripted_agents_map[aid] = LLMAgentWithShield(
                    backend=backend,
                    rbac_policy=rbac_policy_llm,
                    pz_to_engine=pz_to_engine,
                    strict_signatures=use_strict_signatures,
                    key_registry=key_registry_merged,
                    get_private_key=get_private_key_fn,
                    capability_policy=capability_policy_llm,
                )
        elif not is_scale_task and llm_backend == "deterministic_constrained":
            from labtrust_gym.baselines.llm.agent import (
                DeterministicConstrainedBackend,
                LLMAgentWithShield,
            )

            pz_to_engine = _default_pz_to_engine(num_runners=num_runners, num_insiders=num_insiders)
            agent_fault_cfg: dict[str, Any] = {}
            if pipeline_mode == "llm_offline" and repo_root is not None:
                from labtrust_gym.baselines.llm.fault_model import load_llm_fault_model

                agent_fault_cfg = load_llm_fault_model(repo_root) or {}
            for aid in llm_agents:
                if aid not in scripted_agents_map:
                    continue
                inner_backend = DeterministicConstrainedBackend(seed=base_seed, default_action_type="NOOP")
                if agent_fault_cfg:
                    from labtrust_gym.baselines.llm.fault_model_agent import (
                        LLMFaultModelAgentWrapper,
                    )

                    inner_backend = LLMFaultModelAgentWrapper(inner_backend, agent_fault_cfg, base_seed)
                scripted_agents_map[aid] = LLMAgentWithShield(
                    backend=inner_backend,
                    rbac_policy=rbac_policy_llm,
                    pz_to_engine=pz_to_engine,
                    strict_signatures=use_strict_signatures,
                    key_registry=key_registry_merged,
                    get_private_key=get_private_key_fn,
                    capability_policy=capability_policy_llm,
                )
        elif not is_scale_task and llm_backend == "deterministic_policy_v1":
            from labtrust_gym.baselines.llm.agent import LLMAgentWithShield
            from labtrust_gym.baselines.llm.deterministic_policy_backend import (
                DeterministicPolicyBackend,
            )

            pz_to_engine = _default_pz_to_engine(num_runners=num_runners, num_insiders=num_insiders)
            policy_fault_cfg: dict[str, Any] = {}
            if pipeline_mode == "llm_offline" and repo_root is not None:
                from labtrust_gym.baselines.llm.fault_model import load_llm_fault_model

                policy_fault_cfg = load_llm_fault_model(repo_root) or {}
            for aid in llm_agents:
                if aid not in scripted_agents_map:
                    continue
                inner_backend = DeterministicPolicyBackend(seed=base_seed, default_action_type="NOOP")
                if policy_fault_cfg:
                    from labtrust_gym.baselines.llm.fault_model_agent import (
                        LLMFaultModelAgentWrapper,
                    )

                    inner_backend = LLMFaultModelAgentWrapper(inner_backend, policy_fault_cfg, base_seed)
                scripted_agents_map[aid] = LLMAgentWithShield(
                    backend=inner_backend,
                    rbac_policy=rbac_policy_llm,
                    pz_to_engine=pz_to_engine,
                    strict_signatures=use_strict_signatures,
                    key_registry=key_registry_merged,
                    get_private_key=get_private_key_fn,
                    capability_policy=capability_policy_llm,
                )
        elif not is_scale_task and llm_backend == "openai_live":
            from labtrust_gym.baselines.llm.agent import LLMAgentWithShield
            from labtrust_gym.baselines.llm.backends.openai_live import (
                OpenAILiveBackend,
            )
            from labtrust_gym.baselines.llm.credentials import resolve_credentials
            from labtrust_gym.baselines.llm.record_fixtures import RecordingBackend

            pz_to_engine = _default_pz_to_engine(num_runners=num_runners, num_insiders=num_insiders)
            creds = resolve_credentials(llm_backend, repo_root)
            base_backend = OpenAILiveBackend(
                **creds,
                trace_collector=llm_trace_collector,
            )
            backend = RecordingBackend(base_backend) if record_fixtures_path is not None else base_backend
            llm_backend_ref = cast(Any, backend)
            for aid in llm_agents:
                if aid not in scripted_agents_map:
                    continue
                scripted_agents_map[aid] = LLMAgentWithShield(
                    backend=backend,
                    rbac_policy=rbac_policy_llm,
                    pz_to_engine=pz_to_engine,
                    strict_signatures=use_strict_signatures,
                    key_registry=key_registry_merged,
                    get_private_key=get_private_key_fn,
                    capability_policy=capability_policy_llm,
                )
        elif not is_scale_task and llm_backend == "openai_responses":
            from labtrust_gym.baselines.llm.agent import LLMAgentWithShield
            from labtrust_gym.baselines.llm.backends.openai_responses import (
                OpenAILiveResponsesBackend,
            )
            from labtrust_gym.baselines.llm.credentials import resolve_credentials
            from labtrust_gym.baselines.llm.record_fixtures import RecordingBackend

            pz_to_engine = _default_pz_to_engine(num_runners=num_runners, num_insiders=num_insiders)
            creds = resolve_credentials(llm_backend, repo_root)
            from labtrust_gym.policy.prompt_registry import load_use_prompts_v02

            prompts_policy = "v0.2" if load_use_prompts_v02(repo_root) else "v0.1"
            base_backend = OpenAILiveResponsesBackend(
                **creds,
                repo_root=repo_root,
                output_mode=llm_output_mode,
                prompts_policy=prompts_policy,
                trace_collector=llm_trace_collector,
            )
            backend = RecordingBackend(base_backend) if record_fixtures_path is not None else base_backend
            llm_backend_ref = cast(Any, backend)
            for aid in llm_agents:
                if aid not in scripted_agents_map:
                    continue
                scripted_agents_map[aid] = LLMAgentWithShield(
                    backend=backend,
                    rbac_policy=rbac_policy_llm,
                    pz_to_engine=pz_to_engine,
                    strict_signatures=use_strict_signatures,
                    key_registry=key_registry_merged,
                    get_private_key=get_private_key_fn,
                    capability_policy=capability_policy_llm,
                )
        elif not is_scale_task and llm_backend == "ollama_live":
            from labtrust_gym.baselines.llm.agent import LLMAgentWithShield
            from labtrust_gym.baselines.llm.backends.ollama_live import (
                OllamaLiveBackend,
            )
            from labtrust_gym.baselines.llm.record_fixtures import RecordingBackend

            pz_to_engine = _default_pz_to_engine(num_runners=num_runners, num_insiders=num_insiders)
            base_backend = OllamaLiveBackend(model=llm_model)
            backend = RecordingBackend(base_backend) if record_fixtures_path is not None else base_backend
            llm_backend_ref = cast(Any, backend)
            for aid in llm_agents:
                if aid not in scripted_agents_map:
                    continue
                scripted_agents_map[aid] = LLMAgentWithShield(
                    backend=backend,
                    rbac_policy=rbac_policy_llm,
                    pz_to_engine=pz_to_engine,
                    strict_signatures=use_strict_signatures,
                    key_registry=key_registry_merged,
                    get_private_key=get_private_key_fn,
                    capability_policy=capability_policy_llm,
                )
        elif not is_scale_task and llm_backend == "anthropic_live":
            from labtrust_gym.baselines.llm.agent import LLMAgentWithShield
            from labtrust_gym.baselines.llm.backends.anthropic_live import (
                AnthropicLiveBackend,
            )
            from labtrust_gym.baselines.llm.credentials import resolve_credentials
            from labtrust_gym.baselines.llm.record_fixtures import RecordingBackend

            pz_to_engine = _default_pz_to_engine(num_runners=num_runners, num_insiders=num_insiders)
            creds = resolve_credentials(llm_backend, repo_root)
            base_backend = AnthropicLiveBackend(
                **creds,
                trace_collector=llm_trace_collector,
            )
            backend = RecordingBackend(base_backend) if record_fixtures_path is not None else base_backend
            llm_backend_ref = cast(Any, backend)
            for aid in llm_agents:
                if aid not in scripted_agents_map:
                    continue
                scripted_agents_map[aid] = LLMAgentWithShield(
                    backend=backend,
                    rbac_policy=rbac_policy_llm,
                    pz_to_engine=pz_to_engine,
                    strict_signatures=use_strict_signatures,
                    key_registry=key_registry_merged,
                    get_private_key=get_private_key_fn,
                    capability_policy=capability_policy_llm,
                )
        elif not is_scale_task and llm_backend == "openai_hosted":
            from labtrust_gym.baselines.llm.agent import LLMAgentWithShield
            from labtrust_gym.baselines.llm.backends.openai_hosted import (
                OpenAIHostedBackend,
            )
            from labtrust_gym.baselines.llm.record_fixtures import RecordingBackend

            pz_to_engine = _default_pz_to_engine(num_runners=num_runners, num_insiders=num_insiders)
            base_backend = OpenAIHostedBackend()
            backend = RecordingBackend(base_backend) if record_fixtures_path is not None else base_backend
            llm_backend_ref = cast(Any, backend)
            for aid in llm_agents:
                if aid not in scripted_agents_map:
                    continue
                scripted_agents_map[aid] = LLMAgentWithShield(
                    backend=backend,
                    rbac_policy=rbac_policy_llm,
                    pz_to_engine=pz_to_engine,
                    strict_signatures=use_strict_signatures,
                    key_registry=key_registry_merged,
                    get_private_key=get_private_key_fn,
                    capability_policy=capability_policy_llm,
                )
        if not is_scale_task and task_name == "adversarial_disruption":
            from labtrust_gym.baselines.adversary import AdversaryAgent

            scripted_agents_map["adversary_0"] = AdversaryAgent()
        if not is_scale_task and task_name == "insider_key_misuse":
            from labtrust_gym.baselines.insider_adversary import InsiderAdversaryAgent

            scripted_agents_map["adversary_insider_0"] = InsiderAdversaryAgent()

    # MARL at scale: when coord method is marl_ppo and N > N_max, populate scripted_agents_map with PPO per-agent agents.
    if (
        is_scale_task
        and coord_method_for_branch == "marl_ppo"
        and scripted_agents_map is not None
        and scale_probe_state is not None
    ):
        scale_agents_marl = scale_probe_state.get("agents") or []
        pz_to_engine_marl = {
            f"worker_{i}": scale_agents_marl[i]["agent_id"]
            for i in range(len(scale_agents_marl))
            if i < len(scale_agents_marl)
        }
        n_max_marl = int(scale_config_dict.get("coord_propose_actions_max_agents", 50))
        if len(pz_to_engine_marl) > n_max_marl:
            model_path_marl = scale_config_dict.get("model_path")
            if model_path_marl and Path(model_path_marl).exists():
                try:
                    from labtrust_gym.baselines.marl.ppo_agent import MarlPPOPerAgentAgent

                    agent_order_marl = list(pz_to_engine_marl.keys())
                    marl_per_agent = MarlPPOPerAgentAgent(
                        model_path=model_path_marl,
                        agent_order=agent_order_marl,
                        repo_root=repo_root,
                    )
                    for aid in pz_to_engine_marl:
                        scripted_agents_map[aid] = marl_per_agent
                except Exception as e:
                    _LOG.warning(
                        "MARL at scale: failed to populate scripted_agents_map with PPO agents: %s",
                        e,
                    )

    # Scale-capable methods: when N > N_max, populate scripted_agents_map with per-agent LLMAgentWithShield for simulation-centric combine path.
    if repo_root:
        _reg_path = repo_root / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
        if _reg_path.exists():
            try:
                from labtrust_gym.policy.coordination import list_scale_capable_method_ids

                scale_capable_set = frozenset(list_scale_capable_method_ids(_reg_path))
            except Exception:
                scale_capable_set = frozenset({"llm_constrained", "llm_central_planner"})
        else:
            scale_capable_set = frozenset({"llm_constrained", "llm_central_planner"})
    else:
        scale_capable_set = frozenset({"llm_constrained", "llm_central_planner"})
    if (
        is_scale_task
        and coord_method
        and scripted_agents_map is not None
        and scale_probe_state is not None
        and coord_method_for_branch in scale_capable_set
    ):
        scale_agents_sim = scale_probe_state.get("agents") or []
        pz_to_engine_sim = {
            f"worker_{i}": scale_agents_sim[i]["agent_id"]
            for i in range(len(scale_agents_sim))
            if i < len(scale_agents_sim)
        }
        n_max_sim = int(scale_config_dict.get("coord_propose_actions_max_agents", 50))
        if len(pz_to_engine_sim) > n_max_sim:
            try:
                from labtrust_gym.baselines.llm.agent import (
                    DeterministicConstrainedBackend,
                    LLMAgentWithShield,
                )
                from labtrust_gym.engine.rbac import load_rbac_policy
                from labtrust_gym.security.agent_capabilities import load_agent_capabilities

                rbac_path_sim = (repo_root or Path.cwd()) / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
                rbac_policy_sim = load_rbac_policy(rbac_path_sim)
                capability_policy_sim = load_agent_capabilities(repo_root)
                constrained_backend_sim = None
                if llm_backend == "openai_live":
                    from labtrust_gym.baselines.llm.backends.openai_live import (
                        OpenAILiveBackend,
                    )
                    from labtrust_gym.baselines.llm.credentials import resolve_credentials

                    creds = resolve_credentials(llm_backend, repo_root)
                    constrained_backend_sim = OpenAILiveBackend(
                        **creds,
                        model=llm_model,
                    )
                    if llm_backend_ref is None:
                        llm_backend_ref = constrained_backend_sim
                elif llm_backend == "ollama_live":
                    from labtrust_gym.baselines.llm.backends.ollama_live import (
                        OllamaLiveBackend,
                    )

                    constrained_backend_sim = OllamaLiveBackend(model=llm_model)
                    if llm_backend_ref is None:
                        llm_backend_ref = constrained_backend_sim
                elif llm_backend == "anthropic_live":
                    from labtrust_gym.baselines.llm.backends.anthropic_live import (
                        AnthropicLiveBackend,
                    )
                    from labtrust_gym.baselines.llm.credentials import resolve_credentials

                    creds = resolve_credentials(llm_backend, repo_root)
                    constrained_backend_sim = AnthropicLiveBackend(**creds, model=llm_model)
                    if llm_backend_ref is None:
                        llm_backend_ref = constrained_backend_sim
                if constrained_backend_sim is None:
                    constrained_backend_sim = DeterministicConstrainedBackend(
                        seed=base_seed, default_action_type="NOOP"
                    )
                try:
                    from labtrust_gym.online.rate_limit import TokenBucket
                except ImportError:
                    TokenBucket = None
                global_rl_sim = TokenBucket(rate=10.0, capacity=20.0) if TokenBucket else None
                shared_cb_sim = None
                if scale_config_dict.get("shared_circuit_breaker_per_backend"):
                    from labtrust_gym.baselines.llm.throttle import (
                        CircuitBreaker,
                        throttle_config_from_env,
                    )

                    _cb_cfg = throttle_config_from_env()
                    shared_cb_sim = CircuitBreaker(
                        consecutive_threshold=int(_cb_cfg.get("circuit_consecutive_threshold", 5)),
                        cooldown_calls=int(_cb_cfg.get("circuit_cooldown_calls", 10)),
                    )
                max_wait_sim = scale_config_dict.get("global_rate_limit_max_wait_s")
                for aid in pz_to_engine_sim:
                    scripted_agents_map[aid] = LLMAgentWithShield(
                        backend=constrained_backend_sim,
                        rbac_policy=rbac_policy_sim,
                        pz_to_engine=pz_to_engine_sim,
                        strict_signatures=use_strict_signatures,
                        key_registry=key_registry_merged or {},
                        get_private_key=get_private_key_fn or (lambda _: None),
                        capability_policy=capability_policy_sim,
                        global_rate_limiter=global_rl_sim,
                        circuit_breaker=shared_cb_sim,
                        global_rate_limit_max_wait_s=max_wait_sim,
                    )
            except Exception as e:
                _LOG.warning(
                    "Scale-capable per-agent LLM population failed, keeping scripted agents: %s",
                    e,
                )

    run_dir_episodes = (log_path if log_path is not None else Path(out_path)).parent
    start_episode_index = 0
    if resume_from is not None:
        from labtrust_gym.benchmarks.checkpoint import start_episode_index_from_resume

        start_episode_index = start_episode_index_from_resume(Path(resume_from))
        if start_episode_index >= num_episodes:
            _LOG.info(
                "Resume checkpoint reports %d episodes done (>= %d); nothing to run.",
                start_episode_index,
                num_episodes,
            )
            from labtrust_gym.pipeline import get_llm_backend_id, get_pipeline_mode

            results_mode = get_pipeline_mode()
            results_llm_backend_id = get_llm_backend_id() or "none"
            results: dict[str, Any] = {
                "schema_version": RESULTS_SCHEMA_VERSION,
                "pipeline_mode": results_mode,
                "llm_backend_id": results_llm_backend_id,
                "allow_network": allow_network,
                "non_deterministic": results_mode == "llm_live" and allow_network,
                "task": task_name,
                "num_episodes": num_episodes,
                "base_seed": base_seed,
                "seeds": [],
                "config": {
                    "max_steps": task.max_steps,
                    "scripted_agents": task.scripted_agents,
                    "reward_config": task.reward_config,
                    "timing_mode": (initial_state_overrides or {}).get("timing_mode", "explicit"),
                    "coord_method": coord_method,
                    "injection_id": injection_id,
                },
                "policy_versions": _policy_versions(repo_root),
                "git_sha": _git_commit_hash(repo_root),
                "git_commit_hash": _git_commit_hash(repo_root),
                "partner_id": partner_id,
                "policy_fingerprint": policy_fingerprint,
                "agent_baseline_id": f"coord_{coord_method}" if coord_method else "scripted_ops_v1",
                "episodes": [],
                "resumed_nothing_to_run": True,
            }
            out_path.write_text(canonical_json(results), encoding="utf-8")
            return results
        _LOG.info(
            "Resuming from episode %d (checkpoint in %s).",
            start_episode_index,
            resume_from,
        )
    seeds = [base_seed + i for i in range(start_episode_index, num_episodes)]
    episodes_metrics: list[dict[str, Any]] = []

    use_fresh_agents_per_episode = task_name == "adversarial_disruption"
    use_fresh_agents_taskf = task_name == "insider_key_misuse"

    # Create one env for all episodes (same task/config) to avoid per-episode construction and policy reload.
    # For scale tasks with scale_config_override, use the scaled state (includes initial_queue_entries for throughput).
    _cal = (initial_state_overrides or {}).get("calibration")
    if is_scale_task and scale_probe_state is not None and start_episode_index == 0:
        _first_initial_state = dict(scale_probe_state)
        if initial_state_overrides:
            _first_initial_state = {**_first_initial_state, **initial_state_overrides}
        if task_name == "coord_risk" and injection_id:
            _first_initial_state["injection_id"] = injection_id
    else:
        _first_initial_state = task.get_initial_state(seeds[0], calibration=_cal, policy_root=repo_root)
        if initial_state_overrides:
            _first_initial_state = {**_first_initial_state, **initial_state_overrides}
    shared_env = env_factory(
        initial_state=_first_initial_state,
        reward_config=task.reward_config,
        log_path=log_path,
    )

    try:
        from labtrust_gym.logging.step_timing import clear as step_timing_clear

        step_timing_clear()
    except ImportError as e:
        _LOG.debug("Step timing clear not available: %s", e)

    agent_driven_backend = None
    if agent_driven:
        if not coord_method:
            raise ValueError("agent_driven requires coord_method (e.g. llm_central_planner_agentic)")
        from labtrust_gym.benchmarks.agent_driven_driver import (
            DeterministicAgentDrivenBackend,
            DeterministicMultiAgenticBackend,
        )

        if multi_agentic:
            use_parallel = (
                use_parallel_multi_agentic
                and is_scale_task
                and llm_backend
                and shared_env
                and getattr(shared_env, "agents", None)
            )
            if use_parallel:
                try:
                    scale_cfg = scale_config_dict if is_scale_task else {}
                    round_timeout_eff = scale_cfg.get("round_timeout_s", round_timeout_s)
                    max_workers_cfg = scale_cfg.get(
                        "parallel_multi_agentic_max_workers", parallel_multi_agentic_max_workers
                    )
                    rate_rps = float(scale_cfg.get("global_rate_limit_rps", 10.0))
                    rate_cap = float(scale_cfg.get("global_rate_limit_capacity", 20.0))
                    from labtrust_gym.baselines.llm.agent import (
                        DeterministicConstrainedBackend,
                        LLMAgentWithShield,
                    )
                    from labtrust_gym.benchmarks.agent_driven_driver import (
                        ParallelMultiAgenticBackend,
                    )
                    from labtrust_gym.engine.rbac import load_rbac_policy
                    from labtrust_gym.envs.action_contract import ACTION_INDEX_TO_TYPE
                    from labtrust_gym.security.agent_capabilities import load_agent_capabilities

                    scale_agents = (scale_probe_state or {}).get("agents") or []
                    pz_to_engine_scale = {
                        f"worker_{i}": scale_agents[i]["agent_id"]
                        for i in range(len(scale_agents))
                        if i < len(scale_agents)
                    }
                    agent_ids_list = list(shared_env.agents)
                    rbac_path = repo_root / "policy" / "rbac" / "rbac_policy.v0.1.yaml"
                    rbac_policy_par = load_rbac_policy(rbac_path)
                    capability_policy_par = load_agent_capabilities(repo_root)
                    constrained_backend_par = None
                    if llm_backend == "openai_live":
                        from labtrust_gym.baselines.llm.backends.openai_live import (
                            OpenAILiveBackend,
                        )
                        from labtrust_gym.baselines.llm.credentials import resolve_credentials

                        creds = resolve_credentials(llm_backend, repo_root)
                        constrained_backend_par = OpenAILiveBackend(
                            **creds,
                            model=llm_model,
                        )
                        if llm_backend_ref is None:
                            llm_backend_ref = constrained_backend_par
                    elif llm_backend == "ollama_live":
                        from labtrust_gym.baselines.llm.backends.ollama_live import (
                            OllamaLiveBackend,
                        )

                        constrained_backend_par = OllamaLiveBackend(model=llm_model)
                        if llm_backend_ref is None:
                            llm_backend_ref = constrained_backend_par
                    elif llm_backend == "anthropic_live":
                        from labtrust_gym.baselines.llm.backends.anthropic_live import (
                            AnthropicLiveBackend,
                        )
                        from labtrust_gym.baselines.llm.credentials import resolve_credentials

                        creds = resolve_credentials(llm_backend, repo_root)
                        constrained_backend_par = AnthropicLiveBackend(**creds, model=llm_model)
                        if llm_backend_ref is None:
                            llm_backend_ref = constrained_backend_par
                    if constrained_backend_par is None:
                        constrained_backend_par = DeterministicConstrainedBackend(
                            seed=base_seed, default_action_type="NOOP"
                        )
                    try:
                        from labtrust_gym.online.rate_limit import TokenBucket
                    except ImportError:
                        TokenBucket = None
                    global_rl_par = TokenBucket(rate=rate_rps, capacity=rate_cap) if TokenBucket else None
                    shared_cb_par = None
                    if scale_cfg.get("shared_circuit_breaker_per_backend"):
                        from labtrust_gym.baselines.llm.throttle import (
                            CircuitBreaker,
                            throttle_config_from_env,
                        )

                        _cb_cfg = throttle_config_from_env()
                        shared_cb_par = CircuitBreaker(
                            consecutive_threshold=int(_cb_cfg.get("circuit_consecutive_threshold", 5)),
                            cooldown_calls=int(_cb_cfg.get("circuit_cooldown_calls", 10)),
                        )
                    agents_map_par: dict[str, Any] = {}
                    max_wait_par = scale_cfg.get("global_rate_limit_max_wait_s")
                    for aid in agent_ids_list:
                        agents_map_par[aid] = LLMAgentWithShield(
                            backend=constrained_backend_par,
                            rbac_policy=rbac_policy_par,
                            pz_to_engine=pz_to_engine_scale,
                            strict_signatures=False,
                            key_registry={},
                            get_private_key=lambda _: None,
                            capability_policy=capability_policy_par,
                            global_rate_limiter=global_rl_par,
                            circuit_breaker=shared_cb_par,
                            global_rate_limit_max_wait_s=max_wait_par,
                        )

                    def _run_one_agent_submit(driver: Any, a: str, agent: Any) -> None:
                        obs = driver.get_current_obs()
                        o = obs.get("observations", {})
                        agent_obs = o.get(a, {})
                        result = agent.act(agent_obs, a)
                        action_index = result[0]
                        action_info = result[1] if len(result) > 1 else {}
                        action_type = action_info.get("action_type") or ACTION_INDEX_TO_TYPE.get(action_index, "NOOP")
                        args = action_info.get("args", {}) or {}
                        reason_code = (
                            action_info.get("reason_code") if isinstance(action_info.get("reason_code"), str) else ""
                        )
                        driver.submit_my_action(a, action_type, args, reason_code or None)

                    def agent_backend_factory(aid: str):
                        ag = agents_map_par[aid]

                        def run(driver: Any, a: str) -> None:
                            _run_one_agent_submit(driver, a, ag)

                        return run

                    max_workers_par = max_workers_cfg
                    if max_workers_par is None:
                        max_workers_par = min(len(agent_ids_list), 64)
                    agent_driven_backend = ParallelMultiAgenticBackend(
                        agent_backend_factory=agent_backend_factory,
                        max_workers=max_workers_par,
                        round_timeout_s=round_timeout_eff,
                        max_steps_to_run=task.max_steps,
                    )
                except Exception as e:
                    _LOG.warning(
                        "Parallel multi-agentic backend build failed, falling back to DeterministicMultiAgenticBackend: %s",
                        e,
                    )
                    agent_driven_backend = DeterministicMultiAgenticBackend(max_steps_to_run=task.max_steps)
            else:
                agent_driven_backend = DeterministicMultiAgenticBackend(max_steps_to_run=task.max_steps)
        elif llm_backend in ("openai_live", "openai_responses"):
            from labtrust_gym.baselines.llm.backends.openai_agent_driven_backend import (
                OpenAIAgentDrivenBackend,
            )

            agent_driven_backend = OpenAIAgentDrivenBackend()
        else:
            agent_driven_backend = DeterministicAgentDrivenBackend(max_steps_to_run=task.max_steps)

    t0_wall = time.perf_counter()
    if always_record_step_timing:
        try:
            from labtrust_gym.logging.step_timing import force_enable_for_run

            force_enable_for_run(True)
        except ImportError:
            pass
    for i, ep_seed in enumerate(seeds):
        ep_idx = start_episode_index + i
        agents_map = scripted_agents_map
        if use_fresh_agents_per_episode and scripted_agents_map is not None:
            from labtrust_gym.baselines.adversary import AdversaryAgent
            from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
            from labtrust_gym.baselines.scripted_qc import ScriptedQcAgent
            from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
            from labtrust_gym.baselines.scripted_supervisor import (
                ScriptedSupervisorAgent,
            )
            from labtrust_gym.envs.pz_parallel import (
                DEFAULT_DEVICE_IDS,
                DEFAULT_ZONE_IDS,
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
                "qc_0": ScriptedQcAgent(),
                "supervisor_0": ScriptedSupervisorAgent(),
                "adversary_0": AdversaryAgent(),
            }
        if use_fresh_agents_taskf and scripted_agents_map is not None:
            from labtrust_gym.baselines.insider_adversary import InsiderAdversaryAgent
            from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
            from labtrust_gym.baselines.scripted_qc import ScriptedQcAgent
            from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
            from labtrust_gym.baselines.scripted_supervisor import (
                ScriptedSupervisorAgent,
            )
            from labtrust_gym.envs.pz_parallel import (
                DEFAULT_DEVICE_IDS,
                DEFAULT_ZONE_IDS,
            )

            agents_map = {
                "ops_0": ScriptedOpsAgent(),
                "runner_0": ScriptedRunnerAgent(
                    zone_ids=DEFAULT_ZONE_IDS,
                    device_ids=DEFAULT_DEVICE_IDS,
                ),
                "qc_0": ScriptedQcAgent(),
                "supervisor_0": ScriptedSupervisorAgent(),
                "adversary_insider_0": InsiderAdversaryAgent(),
            }
        comms_cfg = None
        if risk_injector_instance is not None and hasattr(risk_injector_instance, "get_comms_config"):
            comms_cfg = risk_injector_instance.get_comms_config()
        if llm_backend_ref is not None and hasattr(llm_backend_ref, "reset_aggregate_metrics"):
            llm_backend_ref.reset_aggregate_metrics()
        if agent_driven and agent_driven_backend is not None:
            from labtrust_gym.benchmarks.agent_driven_driver import (
                run_episode_agent_driven,
            )

            round_timeout_to_use = round_timeout_s
            if is_scale_task and coord_method:
                scale_cfg_rt = scale_config_dict
                if scale_cfg_rt is not None:
                    round_timeout_to_use = scale_cfg_rt.get("round_timeout_s", round_timeout_s)
            ep_initial = (
                _first_initial_state
                if ep_idx == 0
                else task.get_initial_state(
                    ep_seed, calibration=(initial_state_overrides or {}).get("calibration"), policy_root=repo_root
                )
            )
            if initial_state_overrides and ep_idx > 0:
                ep_initial = {**ep_initial, **initial_state_overrides}
            coord_for_driver = coord_method_instance
            if multi_agentic and coord_for_driver is None:
                from dataclasses import asdict

                from labtrust_gym.baselines.coordination.registry import (
                    make_coordination_method,
                )

                scale_cfg = getattr(task, "scale_config", None)
                scale_cfg_dict = asdict(scale_cfg) if scale_cfg is not None else {}
                coord_for_driver = make_coordination_method(
                    coord_method,
                    ep_initial.get("effective_policy") or {},
                    repo_root=repo_root,
                    scale_config=scale_cfg_dict,
                )
            metrics, _ = run_episode_agent_driven(
                task=task,
                episode_seed=ep_seed,
                env_factory=env_factory,
                agent_driven_backend=agent_driven_backend,
                log_path=log_path,
                initial_state_overrides=initial_state_overrides or None,
                risk_injector=risk_injector_instance,
                comms_config=comms_cfg,
                episode_id=ep_idx,
                run_dir=run_dir_episodes,
                metrics_aggregator_id=metrics_aggregator_id,
                repo_root=repo_root,
                env=shared_env,
                mode="multi_agentic" if multi_agentic else "single",
                coord_method=coord_for_driver if multi_agentic else None,
                round_timeout_s=round_timeout_to_use,
            )
        else:
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
                episode_id=ep_idx,
                run_dir=run_dir_episodes,
                metrics_aggregator_id=metrics_aggregator_id,
                repo_root=repo_root,
                env=shared_env,
                log_step_interval=log_step_interval,
                checkpoint_every_n_steps=checkpoint_every_n_steps,
                run_dir_for_checkpoint=run_dir_episodes,
                base_seed_for_checkpoint=base_seed,
                num_episodes_for_checkpoint=num_episodes,
                approval_callback=approval_callback,
            )
        ep_record: dict[str, Any] = {"seed": ep_seed, "metrics": metrics}
        if llm_backend_ref is not None and hasattr(llm_backend_ref, "snapshot_aggregate_metrics"):
            ep_record["llm_episode"] = llm_backend_ref.snapshot_aggregate_metrics()
        episodes_metrics.append(ep_record)
        if progress_callback is not None:
            try:
                progress_callback(ep_idx + 1, num_episodes, metrics)
            except Exception:  # noqa: BLE001
                pass
        if run_dir_episodes is not None and log_path is not None:
            episodes_jsonl = Path(run_dir_episodes) / "episodes.jsonl"
            with open(episodes_jsonl, "a", encoding="utf-8") as f:
                f.write(json.dumps(ep_record, sort_keys=True) + "\n")
        if run_dir_episodes is not None and checkpoint_every_n_episodes is not None and checkpoint_every_n_episodes > 0:
            if (ep_idx + 1) % checkpoint_every_n_episodes == 0:
                from labtrust_gym.benchmarks.checkpoint import write_checkpoint

                write_checkpoint(
                    run_dir_episodes,
                    ep_idx,
                    base_seed,
                    num_episodes,
                )

    if (
        episodes_metrics
        and run_dir_episodes is not None
        and checkpoint_every_n_episodes is not None
        and checkpoint_every_n_episodes > 0
    ):
        last_ep_idx = start_episode_index + len(episodes_metrics) - 1
        if (last_ep_idx + 1) % checkpoint_every_n_episodes != 0:
            from labtrust_gym.benchmarks.checkpoint import write_checkpoint

            write_checkpoint(
                run_dir_episodes,
                last_ep_idx,
                base_seed,
                num_episodes,
            )

    run_duration_wall_s = time.perf_counter() - t0_wall
    run_duration_episodes_per_s = num_episodes / run_duration_wall_s if run_duration_wall_s > 0 else None

    policy_versions = _policy_versions(repo_root)
    git_hash = _git_commit_hash(repo_root)
    partner_id_result = partner_id
    policy_fingerprint_result = policy_fingerprint
    if coord_method:
        agent_baseline_id = f"coord_{coord_method}"
    elif llm_backend in ("deterministic", "deterministic_constrained"):
        agent_baseline_id = "llm_safe_v1"
    elif llm_backend == "openai_live":
        agent_baseline_id = "llm_live_openai_v1"
    elif llm_backend == "openai_hosted":
        agent_baseline_id = "llm_live_openai_hosted_v1"
    elif llm_backend == "openai_responses":
        agent_baseline_id = "llm_live_openai_responses_v1"
    elif llm_backend == "anthropic_live":
        agent_baseline_id = "llm_live_anthropic_v1"
    else:
        agent_baseline_id = (
            "adversary_v1"
            if task_name == "adversarial_disruption"
            else ("insider_v1" if task_name == "insider_key_misuse" else "scripted_ops_v1")
        )

    effective_timing = (initial_state_overrides or {}).get("timing_mode", "explicit")
    results_mode = get_pipeline_mode()  # One of: deterministic | llm_offline | llm_live (see pipeline.py)
    results_llm_backend_id = get_llm_backend_id() or "none"
    non_deterministic = results_mode == "llm_live" and allow_network  # True only for llm_live + network
    results: dict[str, Any] = {
        "schema_version": RESULTS_SCHEMA_VERSION,
        "pipeline_mode": results_mode,  # Always recorded for audit (deterministic | llm_offline | llm_live)
        "llm_backend_id": results_llm_backend_id,
        "llm_model_id": None,
        "allow_network": allow_network,
        "non_deterministic": non_deterministic,
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
    tool_reg_fp_override = (initial_state_overrides or {}).get("tool_registry_fingerprint")
    if tool_reg_fp_override is not None:
        results["tool_registry_fingerprint"] = tool_reg_fp_override

    if llm_backend is not None:
        if llm_backend == "deterministic":
            results["metadata"] = {
                "llm_backend_id": "fixture",
                "llm_model_id": "fixture",
                "llm_error_rate": 0.0,
                "mean_llm_latency_ms": None,
                "estimated_cost_usd": None,
            }
        elif llm_backend == "deterministic_constrained":
            results["metadata"] = {
                "llm_backend_id": "deterministic_constrained",
                "llm_model_id": "n/a",
                "llm_error_rate": 0.0,
                "mean_llm_latency_ms": None,
            }
        elif llm_backend in ("openai_live", "openai_responses") and llm_backend_ref is not None:
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
                "p50_llm_latency_ms": agg.get("p50_latency_ms"),
                "p95_llm_latency_ms": agg.get("p95_latency_ms"),
                "total_tokens": agg.get("total_tokens"),
                "tokens_per_step": agg.get("tokens_per_step"),
                "estimated_cost_usd": agg.get("estimated_cost_usd"),
            }
        elif llm_backend == "anthropic_live" and llm_backend_ref is not None:
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
        elif llm_backend == "openai_hosted":
            inner = getattr(llm_backend_ref, "_inner", llm_backend_ref)
            model_id = getattr(inner, "_model", None) or "gpt-4o-mini"
            results["metadata"] = {
                "llm_backend_id": "openai_hosted",
                "llm_model_id": model_id,
                "llm_error_rate": None,
                "mean_llm_latency_ms": None,
            }
        else:
            results["metadata"] = {
                "llm_backend_id": llm_backend,
                "llm_model_id": None,
                "llm_error_rate": None,
                "mean_llm_latency_ms": None,
            }
    if results.get("metadata") is not None:
        pf = None
        if llm_backend_ref is not None:
            lm = getattr(llm_backend_ref, "last_metrics", None)
            if isinstance(lm, dict):
                pf = lm.get("prompt_fingerprint")
        if pf is None and scripted_agents_map:
            for _aid, agent in scripted_agents_map.items():
                pf = getattr(agent, "_last_prompt_fingerprint", None)
                if pf:
                    break
        if pf is not None:
            results["metadata"]["prompt_fingerprint"] = pf
        if "llm_model_id" in results["metadata"]:
            results["llm_model_id"] = results["metadata"]["llm_model_id"]
    if coord_method_instance is not None:
        pf_coord = getattr(coord_method_instance, "_prompt_fingerprints", None)
        if isinstance(pf_coord, dict) and pf_coord:
            if results.get("metadata") is None:
                results["metadata"] = {}
            results["metadata"]["prompt_template_id"] = pf_coord.get("prompt_template_id")
            results["metadata"]["prompt_sha256"] = pf_coord.get("prompt_sha256")
            results["metadata"]["allowed_actions_payload_sha256"] = pf_coord.get("allowed_actions_payload_sha256")
            results["metadata"]["coordination_policy_fingerprint"] = pf_coord.get("coordination_policy_fingerprint")
            inputs_for_verify = pf_coord.get("prompt_fingerprint_inputs")
            if isinstance(inputs_for_verify, dict):
                out_path_resolved = Path(out_path)
                inputs_path = out_path_resolved.parent / "prompt_fingerprint_inputs.v0.1.json"
                with inputs_path.open("w", encoding="utf-8") as f:
                    json.dump(inputs_for_verify, f, indent=2, sort_keys=True)
        learning_meta = getattr(coord_method_instance, "get_learning_metadata", None)
        if callable(learning_meta):
            learning_dict = learning_meta()
            if isinstance(learning_dict, dict) and learning_dict:
                if results.get("metadata") is None:
                    results["metadata"] = {}
                results["metadata"].setdefault("coordination", {})["learning"] = learning_dict

    trace_env = os.environ.get("LABTRUST_LLM_TRACE", "").strip().lower()
    if trace_env in ("1", "true", "yes"):
        try:
            from labtrust_gym.baselines.llm.llm_tracer import get_llm_tracer

            tracer = get_llm_tracer()
            if tracer is not None:
                results["llm_trace"] = tracer.get_spans()
                summary = tracer.get_attribution_summary()
                if results.get("metadata") is None:
                    results["metadata"] = {}
                results["metadata"]["llm_attribution_summary"] = summary
                tracer.clear()
        except Exception as e:
            _LOG.warning("Failed to collect LLM trace/attribution: %s", e)

    if record_fixtures_path is not None and llm_backend_ref is not None:
        records = getattr(llm_backend_ref, "records", None)
        if isinstance(records, dict) and records:
            from labtrust_gym.baselines.llm.record_fixtures import (
                merge_and_write_fixtures,
            )

            n = merge_and_write_fixtures(records, Path(record_fixtures_path))
            if results.get("metadata") is None:
                results["metadata"] = {}
            results["metadata"]["recorded_fixtures"] = n
            results["metadata"]["record_fixtures_path"] = str(record_fixtures_path)

    if record_coord_fixtures_path is not None and coord_records:
        from labtrust_gym.baselines.llm.record_fixtures_coord import (
            merge_and_write_coord_fixtures,
        )

        n_coord = merge_and_write_coord_fixtures(coord_records, Path(record_coord_fixtures_path))
        if results.get("metadata") is None:
            results["metadata"] = {}
        results["metadata"]["recorded_coord_fixtures"] = n_coord
        results["metadata"]["record_coord_fixtures_path"] = str(record_coord_fixtures_path)

    if results.get("metadata") is None:
        results["metadata"] = {}
    # When always_record_step_timing is True, always write step_timing and run_duration_wall_s (capacity planning).
    if always_record_step_timing:
        results["metadata"]["run_duration_wall_s"] = round(run_duration_wall_s, 3)
        if run_duration_episodes_per_s is not None:
            results["metadata"]["run_duration_episodes_per_s"] = round(run_duration_episodes_per_s, 4)
        try:
            from labtrust_gym.logging.step_timing import (
                clear as step_timing_clear,
            )
            from labtrust_gym.logging.step_timing import (
                force_enable_for_run,
                get_aggregates,
            )

            step_agg = get_aggregates()
            if step_agg:
                results["metadata"]["step_timing"] = step_agg
            force_enable_for_run(False)
            step_timing_clear()
        except ImportError as e:
            _LOG.debug("Step timing not available: %s", e)
    # For deterministic runs (no always_record_step_timing), use fixed values so file is byte-identical.
    elif results.get("non_deterministic"):
        results["metadata"]["run_duration_wall_s"] = round(run_duration_wall_s, 3)
        if run_duration_episodes_per_s is not None:
            results["metadata"]["run_duration_episodes_per_s"] = round(run_duration_episodes_per_s, 4)
        try:
            from labtrust_gym.logging.step_timing import get_aggregates

            step_agg = get_aggregates()
            if step_agg:
                results["metadata"]["step_timing"] = step_agg
        except ImportError as e:
            _LOG.debug("Step timing get_aggregates not available: %s", e)
    else:
        results["metadata"]["run_duration_wall_s"] = 0
        results["metadata"]["run_duration_episodes_per_s"] = None
    results["metadata"]["python_version"] = sys.version.split()[0]
    results["metadata"]["platform"] = sys.platform

    schema_path = repo_root / "policy" / "schemas" / "results.v0.2.schema.json"
    validation_errors = validate_results_v02(results, schema_path=schema_path)
    if validation_errors:
        for msg in validation_errors:
            _LOG.error("%s", msg)
        raise ValueError(f"Results failed schema validation ({len(validation_errors)} error(s)); see stderr")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Deterministic pipeline: write canonical JSON so file is byte-identical across runs
    # (same seed => same content => same hash). Non-deterministic: human-readable indent.
    if results.get("non_deterministic"):
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
    else:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(canonical_json(results) + "\n")

    return results


def main(
    task: str,
    episodes: int,
    seed: int,
    out: str,
    repo_root: Path | None = None,
    log_path: str | None = None,
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
    _LOG.info("Wrote %s", out)
    return 0
