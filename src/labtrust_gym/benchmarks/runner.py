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
from typing import Any, cast

from labtrust_gym.benchmarks.metrics import (
    compute_episode_metrics,
    get_metrics_aggregator,
)
from labtrust_gym.benchmarks.tasks import BenchmarkTask, get_task
from labtrust_gym.baselines.coordination.llm_executor import (
    _proposal_hash,
    shield_outcome_hash_from_step_results,
)
from labtrust_gym.logging.episode_log import (
    EpisodeLogger,
    build_llm_coord_audit_digest_entry,
    build_llm_coord_proposal_entry,
)


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
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _normalize_llm_economics(
    raw_llm: dict[str, Any] | None,
    raw_llm_repair: dict[str, Any] | None,
    steps: int,
) -> dict[str, Any]:
    """
    Build results.v0.2 canonical coordination.llm block: call_count, total_tokens,
    tokens_per_step, mean_latency_ms, p95_latency_ms, error_rate, invalid_output_rate,
    estimated_cost_usd. Fills 0 / null for missing or deterministic.
    """
    raw = raw_llm or {}
    repair = raw_llm_repair or {}
    steps = max(1, steps)

    calls_main = (
        raw.get("call_count")
        if raw.get("call_count") is not None
        else int(raw.get("proposal_total_count") or 0)
    )
    calls_repair = int(repair.get("repair_call_count") or 0)
    call_count = calls_main + calls_repair

    tokens_in = int(raw.get("tokens_in") or 0)
    tokens_out = int(raw.get("tokens_out") or 0)
    tokens_repair = int(repair.get("total_repair_tokens") or 0)
    total_tokens = tokens_in + tokens_out + tokens_repair
    tokens_per_step = round((total_tokens / steps), 4) if total_tokens else 0.0

    lat_list = raw.get("latency_ms_list") or []
    if repair.get("mean_repair_latency_ms") is not None and calls_repair:
        lat_list = list(lat_list) + [
            repair["mean_repair_latency_ms"],
        ] * max(0, calls_repair - 1)
    mean_latency_ms: float | None = raw.get("latency_ms")
    if mean_latency_ms is None and repair.get("mean_repair_latency_ms") is not None:
        mean_latency_ms = repair.get("mean_repair_latency_ms")
    if mean_latency_ms is None and lat_list:
        valid = [float(x) for x in lat_list if x is not None]
        mean_latency_ms = round(sum(valid) / len(valid), 2) if valid else None
    p95_latency_ms: float | None = None
    if lat_list:
        valid = sorted(float(x) for x in lat_list if x is not None)
        if valid:
            k = (len(valid) - 1) * 0.95
            lo = int(k)
            hi = min(lo + 1, len(valid) - 1)
            p95_latency_ms = round(
                valid[lo] + (k - lo) * (valid[hi] - valid[lo]), 2
            )

    invalid_main = 0
    if calls_main and raw.get("proposal_total_count"):
        valid_count = int(raw.get("proposal_valid_count") or 0)
        invalid_main = max(0, int(raw.get("proposal_total_count") or 0) - valid_count)
    invalid_repair = int(repair.get("repair_fallback_noop_count") or 0)
    total_calls = call_count or 1
    invalid_output_rate = round(
        (invalid_main + invalid_repair) / total_calls, 4
    )

    cost = raw.get("estimated_cost_usd")
    if cost is None:
        cost = repair.get("estimated_cost_usd")
    if cost is not None:
        try:
            cost = float(cost)
        except (TypeError, ValueError):
            cost = None

    out = {
        "call_count": call_count,
        "total_tokens": total_tokens,
        "tokens_per_step": tokens_per_step,
        "mean_latency_ms": mean_latency_ms,
        "p95_latency_ms": p95_latency_ms,
        "error_rate": float(raw.get("error_rate") or 0.0),
        "invalid_output_rate": invalid_output_rate,
        "estimated_cost_usd": cost,
    }
    if repair.get("fault_injected_rate") is not None:
        out["fault_injected_rate"] = repair["fault_injected_rate"]
    if repair.get("fallback_rate") is not None:
        out["fallback_rate"] = repair["fallback_rate"]
    return out


def _policy_versions(root: Path) -> dict[str, str]:
    """Read policy file versions (emits vocab, catalogue schema, etc.)."""
    versions: dict[str, str] = {}
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
) -> tuple[dict[str, Any], list[list[dict[str, Any]]]]:
    """
    Run one episode. Returns (metrics_dict, step_results_per_step).

    env_factory: callable(initial_state, reward_config, log_path=?) -> env.
    scripted_agents_map: agent_id -> agent with .act(obs, agent_id) -> (idx, info).
    log_path: optional JSONL path for episode step log (append mode).
    initial_state_overrides: optional dict merged into initial_state (e.g. timing_mode, ablations).
    coord_method: optional CoordinationMethod; when set, propose_actions drives all agents (coord_scale/coord_risk).
    run_dir: optional; when set, passed to coord_method.reset via scale_config for study-track artifacts.
    repo_root: optional policy root; when set, passed to task.get_initial_state as policy_root.
    """
    calibration = (
        initial_state_overrides.get("calibration") if initial_state_overrides else None
    )
    initial_state = task.get_initial_state(
        episode_seed, calibration=calibration, policy_root=repo_root
    )
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
                    str(initial_state.get("timing_mode", "explicit")).strip().lower()
                    or "explicit",
                )
    step_results_per_step: list[list[dict[str, Any]]] = []
    t_s_list: list[int] = []
    dt_s = getattr(env, "_dt_s", 10)
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
            elif getattr(coord_method, "_max_repairs", 0) > 0 and getattr(
                coord_method, "_backend", None
            ) is not None and callable(
                getattr(
                    getattr(coord_method, "_backend", None),
                    "generate_proposal",
                    None,
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
                policy_summary_repair = getattr(
                    coord_method, "_policy_summary", None
                ) or effective_policy or {}
                allowed_repair = getattr(
                    coord_method, "_allowed_actions", None
                ) or ["NOOP", "TICK"]
                backend_repair = getattr(coord_method, "_backend", None)

                def _propose_fn(
                    obs: dict[str, Any],
                    infos: dict[str, dict[str, Any]],
                    t: int,
                    repair_request: dict[str, Any] | None = None,
                ) -> dict[str, Any] | None:
                    digest = build_state_digest(
                        obs, infos, t, policy_summary_repair
                    )
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
                        except Exception:
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
                    if episode_logger_llm is not None and record.get(
                        "log_type"
                    ) == "LLM_COORD_PROPOSAL_ATTEMPT":
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
                    actions_dict = {
                        a: {"action_index": 0}
                        for a in env.agents
                    }
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
                inj_id = (
                    getattr(risk_injector, "injection_id", None)
                    if risk_injector is not None
                    else None
                )
                if (
                    getattr(coord_method, "method_id", None)
                    == "llm_repair_over_kernel_whca"
                    and inj_id in ("INJ-COMMS-POISON-001", "INJ-ID-SPOOF-001")
                ):
                    infos = dict(infos) if isinstance(infos, dict) else {}
                    infos["_coord_repair_triggers"] = (
                        ["comms_poison"]
                        if inj_id == "INJ-COMMS-POISON-001"
                        else ["id_spoof"]
                    )
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
            stale_emit_payloads_this_step: list[dict[str, Any]] = []
            if blackboard_harness is not None:
                from labtrust_gym.coordination.coordination_monitor import (
                    DEFAULT_MAX_STALENESS_MS,
                    check_staleness,
                    count_critical_actions,
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
        if episode_logger_llm is not None:
            last_proposal = getattr(coord_method, "_last_proposal", None)
            last_meta = getattr(coord_method, "_last_meta", None)
            if last_proposal is not None and last_meta is not None:
                prop_hash = _proposal_hash(last_proposal)
                shield_hash = (
                    shield_outcome_hash_this_step
                    or getattr(coord_method, "last_shield_outcome_hash", None)
                    or ""
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
                llm_audit_steps.append({
                    "step_id": step_t,
                    "proposal_hash": prop_hash,
                    "shield_outcome_hash": shield_hash,
                })
        step_results_per_step.append(step_results)
        if coord_method is not None and hasattr(coord_method, "on_step_result"):
            coord_method.on_step_result(step_results)
        t_s_list.append(len(step_results_per_step) * dt_s)
        if (
            timing_mode == "simulated"
            and hasattr(env, "_engine")
            and hasattr(env, "_device_ids")
        ):
            q_per_dev: dict[str, int] = {}
            for dev in getattr(env, "_device_ids", []):
                try:
                    q_per_dev[dev] = int(env._engine.query(f"queue_length('{dev}')"))
                except (ValueError, TypeError):
                    q_per_dev[dev] = 0
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
    aggregator = (
        get_metrics_aggregator(metrics_aggregator_id)
        if metrics_aggregator_id
        else None
    )
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
        queue_lengths_per_step=(
            queue_lengths_per_step if queue_lengths_per_step else None
        ),
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
        hierarchy_metrics = getattr(
            coord_method, "get_hierarchy_metrics", lambda: None
        )()
        if hierarchy_metrics is not None:
            metrics.setdefault("coordination", {})["hierarchy"] = hierarchy_metrics
        llm_metrics = getattr(coord_method, "get_llm_metrics", lambda: None)()
        llm_repair_metrics = getattr(
            coord_method, "get_llm_repair_metrics", lambda: None
        )()
        if llm_repair_metrics is not None:
            metrics.setdefault("coordination", {})["llm_repair"] = llm_repair_metrics
        if llm_metrics is not None or llm_repair_metrics is not None:
            steps_count = metrics.get("steps", 1)
            metrics.setdefault("coordination", {})["llm"] = _normalize_llm_economics(
                llm_metrics, llm_repair_metrics, steps_count
            )
        auction_metrics = getattr(
            coord_method, "get_auction_metrics", lambda: None
        )()
        if auction_metrics is not None:
            metrics.setdefault("coordination", {})["auction"] = auction_metrics
        detection_events = getattr(
            coord_method, "get_detection_events", lambda: []
        )()
        drop_reasons = getattr(
            coord_method, "get_drop_reasons", lambda: []
        )()
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
            metrics["sec"]["detector_recommendation_rate"] = dm.get(
                "detector_recommendation_rate"
            )
            metrics["sec"]["detector_invalid_recommendation_rate"] = dm.get(
                "detector_invalid_recommendation_rate"
            )
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


def _default_pz_to_engine(
    num_runners: int = 2, num_insiders: int = 0
) -> dict[str, str]:
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

    # Resolve pipeline_mode and allow_network (caller may pass explicitly; otherwise infer from llm_backend)
    if pipeline_mode is not None and pipeline_mode not in (
        "deterministic",
        "llm_offline",
        "llm_live",
    ):
        raise ValueError(
            f"pipeline_mode must be deterministic, llm_offline, or llm_live, got {pipeline_mode!r}"
        )
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
    effective_policy: dict[str, Any] | None = None
    policy_fingerprint: str | None = None
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
            except Exception:
                pass
            try:
                from labtrust_gym.auth.authorize import rbac_policy_fingerprint
                from labtrust_gym.engine.rbac import load_rbac_policy

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
    key_registry_merged: dict[str, Any] | None = None
    get_private_key_fn: Any | None = None
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
    is_scale_task = task_name in ("coord_scale", "coord_risk")
    scale_probe_state: dict[str, Any] | None = None
    coord_method_instance: Any | None = None
    if is_scale_task:
        if scale_config_override is not None:
            from labtrust_gym.benchmarks.coordination_scale import (
                generate_scaled_initial_state,
            )

            scale_probe_state = generate_scaled_initial_state(
                scale_config_override, repo_root, base_seed
            )
            task.max_steps = scale_config_override.horizon_steps
            task.scale_config = scale_config_override
        else:
            scale_probe_state = task.get_initial_state(base_seed, policy_root=repo_root)
    if is_scale_task and coord_method:
        from dataclasses import asdict

        from labtrust_gym.baselines.coordination.registry import (
            make_coordination_method,
        )

        _scale_cfg = (
            scale_config_override
            if scale_config_override is not None
            else getattr(task, "scale_config", None)
        )
        scale_config_dict = (
            asdict(scale_config_override)
            if scale_config_override is not None
            else (asdict(_scale_cfg) if _scale_cfg is not None else {})
        )
        if task_name == "coord_risk" and injection_id:
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict["injection_id"] = injection_id
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
            except Exception:
                pass
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
            constrained_backend = None
            if llm_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_live import (
                    OpenAILiveBackend,
                )
                from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
                    require_openai_api_key,
                )
                api_key = require_openai_api_key()
                constrained_backend = OpenAILiveBackend(
                    api_key=api_key,
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
                constrained_backend = AnthropicLiveBackend(model=llm_model)
                llm_backend_ref = constrained_backend
            if constrained_backend is None:
                constrained_backend = DeterministicConstrainedBackend(
                    seed=base_seed, default_action_type="NOOP"
                )
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
        elif coord_method_for_branch == "llm_central_planner":
            scale_agents = (scale_probe_state or {}).get("agents") or []
            pz_to_engine_central = {
                f"worker_{i}": scale_agents[i]["agent_id"]
                for i in range(len(scale_agents))
                if i < len(scale_agents)
            }
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict.setdefault("seed", base_seed)
            policy_for_coord = (policy_for_coord or {}).copy()
            policy_for_coord.setdefault("pz_to_engine", pz_to_engine_central)
            proposal_backend = None
            if llm_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
                    OpenAICoordinationProposalBackend,
                    require_openai_api_key,
                )
                api_key = require_openai_api_key()
                proposal_backend = OpenAICoordinationProposalBackend(
                    api_key=api_key,
                    model=llm_model,
                    repo_root=repo_root,
                )
                llm_backend_ref = proposal_backend
            elif llm_backend == "ollama_live":
                from labtrust_gym.baselines.llm.backends.ollama_coordination_backend import (
                    OllamaCoordinationProposalBackend,
                )
                proposal_backend = OllamaCoordinationProposalBackend()
                llm_backend_ref = proposal_backend
            elif llm_backend == "anthropic_live":
                from labtrust_gym.baselines.llm.backends.anthropic_live import (
                    AnthropicCoordinationProposalBackend,
                )
                proposal_backend = AnthropicCoordinationProposalBackend(
                    model=llm_model,
                    repo_root=repo_root,
                )
                llm_backend_ref = proposal_backend
            if proposal_backend is None and repo_root is not None:
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
                    "llm_central_planner requires proposal_backend= or repo_root "
                    "for deterministic backend"
                )
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
                f"worker_{i}": scale_agents[i]["agent_id"]
                for i in range(len(scale_agents))
                if i < len(scale_agents)
            }
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict.setdefault("seed", base_seed)
            policy_for_coord = (policy_for_coord or {}).copy()
            policy_for_coord.setdefault("pz_to_engine", pz_to_engine_hier)
            allocator_backend = None
            if llm_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
                    OpenAICoordinationProposalBackend,
                    require_openai_api_key,
                )
                api_key = require_openai_api_key()
                allocator_backend = OpenAICoordinationProposalBackend(
                    api_key=api_key,
                    model=llm_model,
                    repo_root=repo_root,
                )
                llm_backend_ref = allocator_backend
            elif llm_backend == "ollama_live":
                from labtrust_gym.baselines.llm.backends.ollama_coordination_backend import (
                    OllamaCoordinationProposalBackend,
                )
                allocator_backend = OllamaCoordinationProposalBackend()
                llm_backend_ref = allocator_backend
            elif llm_backend == "anthropic_live":
                from labtrust_gym.baselines.llm.backends.anthropic_live import (
                    AnthropicCoordinationProposalBackend,
                )
                allocator_backend = AnthropicCoordinationProposalBackend(
                    model=llm_model,
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
                    "llm_hierarchical_allocator requires allocator_backend= or repo_root "
                    "for deterministic backend"
                )
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
                f"worker_{i}": scale_agents[i]["agent_id"]
                for i in range(len(scale_agents))
                if i < len(scale_agents)
            }
            scale_config_dict = dict(scale_config_dict)
            scale_config_dict.setdefault("seed", base_seed)
            if task_name == "coord_risk" and injection_id:
                scale_config_dict["injection_id"] = injection_id
            policy_for_coord = (policy_for_coord or {}).copy()
            policy_for_coord.setdefault("pz_to_engine", pz_to_engine_auc)
            bid_backend = None
            if llm_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_bid_backend import (
                    OpenAIBidBackend,
                )
                from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
                    require_openai_api_key,
                )
                api_key = require_openai_api_key()
                bid_backend = OpenAIBidBackend(
                    api_key=api_key,
                    model=llm_model,
                    repo_root=repo_root,
                )
                llm_backend_ref = bid_backend
            elif llm_backend == "ollama_live":
                from labtrust_gym.baselines.llm.backends.ollama_coordination_backend import (
                    OllamaBidBackend,
                )
                bid_backend = OllamaBidBackend()
                llm_backend_ref = bid_backend
            elif llm_backend == "anthropic_live":
                from labtrust_gym.baselines.llm.backends.anthropic_live import (
                    AnthropicBidBackend,
                )
                bid_backend = AnthropicBidBackend(model=llm_model, repo_root=repo_root)
                llm_backend_ref = bid_backend
            if bid_backend is None and repo_root is not None:
                from labtrust_gym.baselines.coordination.methods.llm_auction_bidder import (
                    DeterministicBidBackend,
                )
                seed = int(scale_config_dict.get("seed", base_seed))
                bid_backend = DeterministicBidBackend(seed=seed)
            if bid_backend is None:
                raise ValueError(
                    "llm_auction_bidder requires bid_backend= or repo_root "
                    "for deterministic backend"
                )
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
                f"worker_{i}": scale_agents[i]["agent_id"]
                for i in range(len(scale_agents))
                if i < len(scale_agents)
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
                    require_openai_api_key,
                )
                api_key = require_openai_api_key()
                summary_backend_gossip = OpenAIGossipSummaryBackend(
                    api_key=api_key,
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
                f"worker_{i}": scale_agents[i]["agent_id"]
                for i in range(len(scale_agents))
                if i < len(scale_agents)
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
                    require_openai_api_key,
                )
                api_key = require_openai_api_key()
                local_proposal_backend = OpenAILocalProposalBackend(
                    api_key=api_key,
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
            repair_backend_param = None
            if llm_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_live import (
                    OpenAILiveBackend,
                )
                from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
                    require_openai_api_key,
                )
                from labtrust_gym.baselines.coordination.methods.llm_repair_over_kernel_whca import (
                    LiveRepairBackend,
                )
                api_key = require_openai_api_key()
                repair_backend_param = LiveRepairBackend(
                    OpenAILiveBackend(api_key=api_key, model=llm_model)
                )
                llm_backend_ref = repair_backend_param._backend
            elif llm_backend == "ollama_live":
                from labtrust_gym.baselines.llm.backends.ollama_live import (
                    OllamaLiveBackend,
                )
                from labtrust_gym.baselines.coordination.methods.llm_repair_over_kernel_whca import (
                    LiveRepairBackend,
                )
                repair_backend_param = LiveRepairBackend(
                    OllamaLiveBackend(model=llm_model)
                )
                llm_backend_ref = repair_backend_param._backend
            elif llm_backend == "anthropic_live":
                from labtrust_gym.baselines.llm.backends.anthropic_live import (
                    AnthropicLiveBackend,
                )
                from labtrust_gym.baselines.coordination.methods.llm_repair_over_kernel_whca import (
                    LiveRepairBackend,
                )
                repair_backend_param = LiveRepairBackend(
                    AnthropicLiveBackend(model=llm_model)
                )
                llm_backend_ref = repair_backend_param._backend
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
            if llm_backend == "openai_live":
                from labtrust_gym.baselines.llm.backends.openai_live import (
                    OpenAILiveBackend,
                )
                from labtrust_gym.baselines.llm.backends.openai_responses_backend import (
                    require_openai_api_key,
                )
                from labtrust_gym.baselines.coordination.assurance import (
                    LiveDetectorBackend,
                )
                api_key = require_openai_api_key()
                live_backend = OpenAILiveBackend(api_key=api_key, model=llm_model)
                scale_config_dict["detector_backend"] = LiveDetectorBackend(
                    live_backend
                )
                llm_backend_ref = live_backend
            elif llm_backend == "ollama_live":
                from labtrust_gym.baselines.llm.backends.ollama_live import (
                    OllamaLiveBackend,
                )
                from labtrust_gym.baselines.coordination.assurance import (
                    LiveDetectorBackend,
                )
                live_backend = OllamaLiveBackend(model=llm_model)
                scale_config_dict["detector_backend"] = LiveDetectorBackend(
                    live_backend
                )
                llm_backend_ref = live_backend
            elif llm_backend == "anthropic_live":
                from labtrust_gym.baselines.llm.backends.anthropic_live import (
                    AnthropicLiveBackend,
                )
                from labtrust_gym.baselines.coordination.assurance import (
                    LiveDetectorBackend,
                )
                live_backend = AnthropicLiveBackend(model=llm_model)
                scale_config_dict["detector_backend"] = LiveDetectorBackend(
                    live_backend
                )
                llm_backend_ref = live_backend
            coord_method_instance = make_coordination_method(
                coord_method,
                policy_for_coord,
                repo_root=repo_root,
                scale_config=scale_config_dict,
            )
        else:
            coord_method_instance = make_coordination_method(
                coord_method,
                policy_for_coord,
                repo_root=repo_root,
                scale_config=scale_config_dict,
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

            spec_path = (
                repo_root
                / "policy"
                / "coordination"
                / "coordination_study_spec.v0.1.yaml"
            )
            intensity = 0.2
            seed_offset = 0
            application_phase: str | None = None
            early_step_cap_spec: int | None = None
            late_step_min_spec: int | None = None
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
                            application_phase = inj.get("application_phase") or None
                            ec = inj.get("early_step_cap")
                            early_step_cap_spec = int(ec) if ec is not None else None
                            lm = inj.get("late_step_min")
                            late_step_min_spec = int(lm) if lm is not None else None
                            break
                except Exception:
                    pass
            # Fallback: load application_phase / step bounds from injections.v0.2.yaml
            if (application_phase is None or early_step_cap_spec is None or late_step_min_spec is None) and repo_root:
                inj_policy_path = repo_root / "policy" / "coordination" / "injections.v0.2.yaml"
                if inj_policy_path.is_file():
                    try:
                        from labtrust_gym.policy.loader import load_yaml
                        inj_data = load_yaml(inj_policy_path)
                        for inj in (inj_data.get("injections") or []):
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
                    except Exception:
                        pass
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

        num_adversaries = (
            1 if task_name == "adversarial_disruption" else 0
        )
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
                1 if task_name == "insider_key_misuse" else 0
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
                FixtureBackend,
                LLMAgentWithShield,
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
            backend = FixtureBackend(repo_root=repo_root)
            llm_backend_ref = cast(Any, backend)
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
        elif not is_scale_task and llm_backend == "deterministic_constrained":
            from labtrust_gym.baselines.llm.agent import (
                DeterministicConstrainedBackend,
                LLMAgentWithShield,
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
            backend = OpenAILiveBackend(trace_collector=llm_trace_collector)
            llm_backend_ref = cast(Any, backend)
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
        elif not is_scale_task and llm_backend == "openai_responses":
            from labtrust_gym.baselines.llm.agent import LLMAgentWithShield
            from labtrust_gym.baselines.llm.backends.openai_responses import (
                OpenAILiveResponsesBackend,
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
            from labtrust_gym.policy.prompt_registry import load_use_prompts_v02

            prompts_policy = "v0.2" if load_use_prompts_v02(repo_root) else "v0.1"
            backend = OpenAILiveResponsesBackend(
                repo_root=repo_root,
                output_mode=llm_output_mode,
                prompts_policy=prompts_policy,
                trace_collector=llm_trace_collector,
            )
            llm_backend_ref = cast(Any, backend)
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
            backend = cast(Any, OllamaLiveBackend())
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
        elif not is_scale_task and llm_backend == "anthropic_live":
            from labtrust_gym.baselines.llm.agent import LLMAgentWithShield
            from labtrust_gym.baselines.llm.backends.anthropic_live import (
                AnthropicLiveBackend,
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
            backend = AnthropicLiveBackend(trace_collector=llm_trace_collector)
            llm_backend_ref = cast(Any, backend)
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
        elif not is_scale_task and llm_backend == "openai_hosted":
            from labtrust_gym.baselines.llm.agent import LLMAgentWithShield
            from labtrust_gym.baselines.llm.backends.openai_hosted import (
                OpenAIHostedBackend,
            )
            from labtrust_gym.baselines.llm.record_fixtures import RecordingBackend
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
            base_backend = OpenAIHostedBackend()
            backend = (
                RecordingBackend(base_backend)
                if record_fixtures_path is not None
                else base_backend
            )
            llm_backend_ref = cast(Any, backend)
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
        if not is_scale_task and task_name == "adversarial_disruption":
            from labtrust_gym.baselines.adversary import AdversaryAgent

            scripted_agents_map["adversary_0"] = AdversaryAgent()
        if not is_scale_task and task_name == "insider_key_misuse":
            from labtrust_gym.baselines.insider_adversary import InsiderAdversaryAgent

            scripted_agents_map["adversary_insider_0"] = InsiderAdversaryAgent()

    seeds = [base_seed + i for i in range(num_episodes)]
    episodes_metrics: list[dict[str, Any]] = []
    run_dir_episodes = (log_path if log_path is not None else Path(out_path)).parent

    use_fresh_agents_per_episode = task_name == "adversarial_disruption"
    use_fresh_agents_taskf = task_name == "insider_key_misuse"

    for ep_idx, ep_seed in enumerate(seeds):
        agents_map = scripted_agents_map
        if use_fresh_agents_per_episode and scripted_agents_map is not None:
            from labtrust_gym.baselines.adversary import AdversaryAgent
            from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
            from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
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
                "adversary_0": AdversaryAgent(),
            }
        if use_fresh_agents_taskf and scripted_agents_map is not None:
            from labtrust_gym.baselines.insider_adversary import InsiderAdversaryAgent
            from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
            from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
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
                "adversary_insider_0": InsiderAdversaryAgent(),
            }
        comms_cfg = None
        if risk_injector_instance is not None and hasattr(
            risk_injector_instance, "get_comms_config"
        ):
            comms_cfg = risk_injector_instance.get_comms_config()
        if llm_backend_ref is not None and hasattr(
            llm_backend_ref, "reset_aggregate_metrics"
        ):
            llm_backend_ref.reset_aggregate_metrics()
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
        )
        ep_record: dict[str, Any] = {"seed": ep_seed, "metrics": metrics}
        if llm_backend_ref is not None and hasattr(
            llm_backend_ref, "snapshot_aggregate_metrics"
        ):
            ep_record["llm_episode"] = llm_backend_ref.snapshot_aggregate_metrics()
        episodes_metrics.append(ep_record)

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
            else (
                "insider_v1"
                if task_name == "insider_key_misuse"
                else "scripted_ops_v1"
            )
        )

    effective_timing = (initial_state_overrides or {}).get("timing_mode", "explicit")
    results_mode = get_pipeline_mode()
    results_llm_backend_id = get_llm_backend_id() or "none"
    non_deterministic = results_mode == "llm_live" and allow_network
    results: dict[str, Any] = {
        "schema_version": "0.2",
        "pipeline_mode": results_mode,
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
    tool_reg_fp_override = (initial_state_overrides or {}).get(
        "tool_registry_fingerprint"
    )
    if tool_reg_fp_override is not None:
        results["tool_registry_fingerprint"] = tool_reg_fp_override

    if llm_backend is not None:
        if llm_backend == "deterministic":
            results["metadata"] = {
                "llm_backend_id": "fixture",
                "llm_model_id": "fixture",
                "llm_error_rate": 0.0,
                "mean_llm_latency_ms": None,
            }
        elif llm_backend == "deterministic_constrained":
            results["metadata"] = {
                "llm_backend_id": "deterministic_constrained",
                "llm_model_id": "n/a",
                "llm_error_rate": 0.0,
                "mean_llm_latency_ms": None,
            }
        elif (
            llm_backend in ("openai_live", "openai_responses")
            and llm_backend_ref is not None
        ):
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
            results["metadata"]["allowed_actions_payload_sha256"] = pf_coord.get(
                "allowed_actions_payload_sha256"
            )
            results["metadata"]["coordination_policy_fingerprint"] = pf_coord.get(
                "coordination_policy_fingerprint"
            )
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
        except Exception:
            pass

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
    print(f"Wrote {out}", file=sys.stderr)
    return 0
