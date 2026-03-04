"""
Coordination study runner: (scale x method x injection) matrix with summary and Pareto report.

Runs the benchmark for each cell of the coordination study spec (scale, method,
injection), writes per-cell results, aggregated summary CSV, and Pareto front
markdown. Reuses study_runner patterns and run_benchmark with scale overrides.
Supports LLM (large language model) coordination methods via --llm-backend and
--llm-model; when unset, only non-LLM methods from the spec are run.
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import os
from pathlib import Path
from typing import Any

# Method IDs that use LLM; only included in the study when --llm-backend is set.
# Includes base methods and defended variants (shielded, safe_fallback).
LLM_METHOD_IDS = frozenset(
    {
        "llm_central_planner",
        "llm_hierarchical_allocator",
        "llm_auction_bidder",
        "llm_central_planner_shielded",
        "llm_hierarchical_allocator_shielded",
        "llm_auction_bidder_shielded",
        "llm_central_planner_with_safe_fallback",
        "llm_hierarchical_allocator_with_safe_fallback",
        "llm_auction_bidder_with_safe_fallback",
        "llm_gossip_summarizer",
        "llm_local_decider_signed_bus",
        "llm_repair_over_kernel_whca",
        "llm_constrained",
        "llm_detector_throttle_advisor",
    }
)

from labtrust_gym.benchmarks.coordination_scale import CoordinationScaleConfig
from labtrust_gym.benchmarks.rate_uncertainty import (
    clopper_pearson_ci,
    worst_case_success_rate_upper,
)
from labtrust_gym.benchmarks.runner import run_benchmark
from labtrust_gym.policy.coordination import (
    get_required_bench_cells,
    injection_id_to_risk_ids_map,
    load_coordination_study_spec,
    load_method_risk_matrix,
    load_risk_to_injection_map,
)
from labtrust_gym.studies.resilience_scoring import (
    compute_components,
    compute_resilience_score,
    load_resilience_scoring_policy,
)

# Default role_mix for scale config (matches tasks._default_scale_config)
_DEFAULT_ROLE_MIX = {
    "ROLE_RUNNER": 0.4,
    "ROLE_ANALYTICS": 0.3,
    "ROLE_RECEPTION": 0.2,
    "ROLE_QC": 0.05,
    "ROLE_SUPERVISOR": 0.05,
}


def _expand_scale_rows(
    spec: dict[str, Any],
    repo_root: Path | None = None,
) -> list[tuple[str, dict[str, Any], CoordinationScaleConfig]]:
    """
    Expand spec scales into Cartesian product of scale dimensions.
    Returns list of (scale_id, scale_row_dict, CoordinationScaleConfig).
    When a scale dimension is "scale_preset", loads CoordinationScaleConfig by id from
    policy/coordination/scale_configs.v0.1.yaml (repo_root required).
    """
    from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id

    scales_def = spec.get("scales") or []
    root = Path(repo_root) if repo_root else Path.cwd()
    if not scales_def:
        scale_row: dict[str, Any] = {}
        scale_config = CoordinationScaleConfig(
            num_agents_total=2,
            role_mix=dict(_DEFAULT_ROLE_MIX),
            num_devices_per_type={"CHEM_ANALYZER": 2, "CENTRIFUGE_BANK": 1},
            num_sites=1,
            specimens_per_min=1.0,
            horizon_steps=200,
            timing_mode="explicit",
        )
        return [("scale_0", scale_row, scale_config)]

    names = [s["name"] for s in scales_def if isinstance(s, dict) and s.get("name")]
    value_lists = []
    for s in scales_def:
        if not isinstance(s, dict):
            continue
        vals = s.get("values")
        if isinstance(vals, list):
            value_lists.append(vals)
        else:
            value_lists.append([vals] if vals is not None else [None])

    if not names or len(names) != len(value_lists):
        scale_config = CoordinationScaleConfig(
            num_agents_total=2,
            role_mix=dict(_DEFAULT_ROLE_MIX),
            num_devices_per_type={"CHEM_ANALYZER": 2, "CENTRIFUGE_BANK": 1},
            num_sites=1,
            specimens_per_min=1.0,
            horizon_steps=200,
            timing_mode="explicit",
        )
        return [("scale_0", {}, scale_config)]

    use_named_preset = "scale_preset" in names
    rows: list[tuple[str, dict[str, Any], CoordinationScaleConfig]] = []
    for idx, combo in enumerate(itertools.product(*value_lists)):
        row = dict(zip(names, combo))
        if use_named_preset and row.get("scale_preset"):
            try:
                scale_config = load_scale_config_by_id(root, str(row["scale_preset"]))
            except (KeyError, FileNotFoundError, ValueError):
                scale_config = CoordinationScaleConfig(
                    num_agents_total=2,
                    role_mix=dict(_DEFAULT_ROLE_MIX),
                    num_devices_per_type={"CHEM_ANALYZER": 2, "CENTRIFUGE_BANK": 1},
                    num_sites=1,
                    specimens_per_min=1.0,
                    horizon_steps=200,
                    timing_mode="explicit",
                )
        else:
            num_agents = int(row.get("num_agents", 2))
            num_sites = int(row.get("num_sites", 1))
            num_devices = int(row.get("num_devices", 2))
            arrival_rate = float(row.get("arrival_rate", 1.0))
            horizon_steps = int(row.get("horizon_steps", 200))
            scale_config = CoordinationScaleConfig(
                num_agents_total=num_agents,
                role_mix=dict(_DEFAULT_ROLE_MIX),
                num_devices_per_type={"CHEM_ANALYZER": num_devices, "CENTRIFUGE_BANK": 1},
                num_sites=num_sites,
                specimens_per_min=arrival_rate,
                horizon_steps=horizon_steps,
                timing_mode="explicit",
            )
        scale_id = "scale_" + "_".join(f"{k}_{v}" for k, v in sorted(row.items()))
        rows.append((scale_id, row, scale_config))
    return rows


def _expand_injections(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Return list of injection config dicts (injection_id, intensity, seed_offset)."""
    injections = spec.get("injections") or []
    out = []
    for inj in injections:
        if isinstance(inj, dict) and inj.get("injection_id"):
            out.append(
                {
                    "injection_id": str(inj["injection_id"]),
                    "intensity": float(inj.get("intensity", 0.2)),
                    "seed_offset": int(inj.get("seed_offset", 0)),
                }
            )
        elif isinstance(inj, str):
            out.append({"injection_id": inj, "intensity": 0.2, "seed_offset": 0})
    return out


def _coverage_preflight(
    spec: dict[str, Any],
    repo_root: Path,
    summary_dir: Path,
    injections: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    For every required_bench risk_id, ensure at least one spec injection covers it (or risk is waived).
    Returns list of missing coverage items; writes summary/coverage_missing.json when non-empty.
    When LABTRUST_STRICT_COVERAGE=1 and missing non-empty, raises SystemExit(1).
    """
    matrix_path = repo_root / "policy" / "coordination" / "method_risk_matrix.v0.1.yaml"
    map_path = repo_root / "policy" / "coordination" / "risk_to_injection_map.v0.1.yaml"
    registry_path = repo_root / "policy" / "risks" / "risk_registry.v0.1.yaml"
    if not matrix_path.is_file():
        return []
    matrix = load_method_risk_matrix(matrix_path)
    required_cells = get_required_bench_cells(matrix)
    required_risk_ids: set[str] = set()
    for c in required_cells:
        if isinstance(c, dict):
            rid = (c.get("risk_id") or "").strip()
            if rid:
                required_risk_ids.add(rid)

    risk_to_injection_ids: dict[str, list[str]] = load_risk_to_injection_map(map_path)
    try:
        from labtrust_gym.policy.risks import load_risk_registry

        registry = load_risk_registry(registry_path)
        for rid in required_risk_ids:
            if rid not in risk_to_injection_ids and registry.risks.get(rid):
                suggested = registry.risks[rid].get("suggested_injections")
                if isinstance(suggested, list):
                    risk_to_injection_ids.setdefault(rid, [str(x) for x in suggested if x])
    except Exception:
        pass

    spec_injection_ids: set[str] = set()
    for inj in injections:
        iid = (inj.get("injection_id") or "").strip()
        if iid:
            spec_injection_ids.add(iid)

    waived: set[str] = set()
    for w in spec.get("waived_risks") or []:
        if isinstance(w, dict) and w.get("risk_id"):
            waived.add(str(w["risk_id"]).strip())

    missing: list[dict[str, Any]] = []
    for risk_id in sorted(required_risk_ids):
        if risk_id in waived:
            continue
        covering = risk_to_injection_ids.get(risk_id) or []
        if not covering:
            missing.append(
                {
                    "risk_id": risk_id,
                    "covering_injection_ids": [],
                    "message": "No mapping for risk_id (add to risk_to_injection_map or risk_registry.suggested_injections).",
                }
            )
            continue
        overlap = [x for x in covering if x in spec_injection_ids]
        if not overlap:
            missing.append(
                {
                    "risk_id": risk_id,
                    "covering_injection_ids": covering,
                    "message": f"Study spec has no injection covering this risk. Add one of: {covering[:5]}{'...' if len(covering) > 5 else ''}",
                }
            )

    if missing:
        summary_dir.mkdir(parents=True, exist_ok=True)
        out_path = summary_dir / "coverage_missing.json"
        payload = {
            "missing": missing,
            "required_risk_ids": sorted(required_risk_ids),
            "spec_injection_ids": sorted(spec_injection_ids),
        }
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        if os.environ.get("LABTRUST_STRICT_COVERAGE", "").strip() in ("1", "true", "yes"):
            msg = (
                f"Coverage integrity gate failed: {len(missing)} required risk(s) have no covering injection in the study spec. "
                f"Missing: {[m['risk_id'] for m in missing]}. See {out_path}. "
                "Add injections or waived_risks in the spec, or set LABTRUST_STRICT_COVERAGE=0 to warn only."
            )
            raise SystemExit(1, msg)
    return missing


def _cell_seed(seed_base: int, scale_idx: int, method_idx: int, injection_idx: int) -> int:
    """Deterministic cell seed (stable across runs)."""
    return seed_base + scale_idx * 10000 + method_idx * 100 + injection_idx


def _empty_cell_metrics() -> dict[str, Any]:
    """Return empty cell metrics dict (all keys, None/0 where appropriate)."""
    return {
        "perf.throughput": 0.0,
        "perf.p95_tat": None,
        "safety.violations_total": 0,
        "safety.blocks_total": 0,
        "sec.attack_success_rate": None,
        "sec.attack_success_rate_ci_lower": None,
        "sec.attack_success_rate_ci_upper": None,
        "sec.worst_case_attack_success_upper_95": None,
        "sec.attack_success_observed": None,
        "sec.detection_latency_steps": None,
        "sec.containment_time_steps": None,
        "sec.stealth_success_rate": None,
        "sec.time_to_attribution_steps": None,
        "sec.blast_radius_proxy": None,
        "robustness.resilience_score": None,
        "comm.msg_count": None,
        "comm.p95_latency_ms": None,
        "comm.drop_rate": None,
        "comm.partition_events": None,
        "coordination.stale_action_rate": None,
        "coordination.deadlock_avoids": None,
        "proposal_valid_rate": None,
        "blocked_rate": None,
        "repair_rate": None,
        "tokens_per_step": None,
        "p95_llm_latency_ms": None,
        "cost.total_tokens": 0,
        "cost.estimated_cost_usd": None,
        "llm.error_rate": 0.0,
        "llm.invalid_output_rate": None,
    }


def _aggregate_cell_metrics(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate episode metrics for one cell: throughput, p95_tat, violations, blocks, sec.*, comm.*, coordination.timing, coordination.route (deadlock_avoids), and when present coordination.llm (proposal_valid_rate, blocked_rate, repair_rate, tokens_per_step, p95_llm_latency_ms)."""
    if not episodes:
        out = _empty_cell_metrics()
        return out
    n = len(episodes)
    throughputs = []
    p95_list = []
    violations_total = 0
    blocks_total = 0
    attack_success_sum = 0.0
    attack_success_observed_sum = 0.0
    detection_steps: list[int | None] = []
    containment_steps: list[int | None] = []
    stealth_success_sum = 0.0
    time_to_attribution_list: list[int | None] = []
    blast_radius_list: list[float | None] = []
    resilience_list: list[float | None] = []
    msg_counts: list[float] = []
    p95_latency_ms_list: list[float | None] = []
    drop_rates: list[float | None] = []
    partition_events_list: list[int | None] = []
    stale_rates: list[float | None] = []
    deadlock_avoids_list: list[float | None] = []
    proposal_valid_rates: list[float] = []
    blocked_rates: list[float] = []
    repair_rates: list[float] = []
    tokens_per_step_list: list[float | None] = []
    llm_latency_ms_list: list[float | None] = []
    cost_total_tokens_list: list[int] = []
    cost_estimated_usd_list: list[float | None] = []
    llm_error_rates: list[float] = []
    llm_invalid_output_rates: list[float] = []

    for ep in episodes:
        m = ep.get("metrics") or {}
        throughputs.append(m.get("throughput", 0))
        vbi = m.get("violations_by_invariant_id") or {}
        violations_total += sum(vbi.values())
        bbr = m.get("blocked_by_reason_code") or {}
        blocks_total += sum(bbr.values())
        p95_list.append(m.get("p95_turnaround_s"))
        sec = m.get("sec") or {}
        attack_success_sum += 1.0 if sec.get("attack_success_rate") else 0.0
        attack_success_observed_sum += 1.0 if sec.get("attack_success_observed") else 0.0
        detection_steps.append(sec.get("detection_latency_steps"))
        containment_steps.append(sec.get("containment_time_steps"))
        stealth_success_sum += 1.0 if sec.get("stealth_success_rate") else 0.0
        time_to_attribution_list.append(sec.get("time_to_attribution_steps"))
        blast_radius_list.append(sec.get("blast_radius_proxy"))
        rob = m.get("robustness") or {}
        resilience_list.append(rob.get("resilience_score"))
        coord = m.get("coordination") or {}
        comm = coord.get("comm") or {}
        msg_counts.append(comm.get("msg_count", 0))
        p95_latency_ms_list.append(comm.get("p95_latency_ms"))
        drop_rates.append(comm.get("drop_rate"))
        partition_events_list.append(comm.get("partition_events"))
        timing = coord.get("timing") or {}
        stale_rates.append(timing.get("stale_action_rate"))
        route = coord.get("route") or {}
        deadlock_avoids_list.append(route.get("deadlock_avoids"))
        llm = coord.get("llm") or {}
        if llm.get("proposal_validity_rate") is not None:
            proposal_valid_rates.append(float(llm["proposal_validity_rate"]))
        if llm.get("blocked_rate") is not None:
            blocked_rates.append(float(llm["blocked_rate"]))
        if llm.get("repair_rate") is not None:
            repair_rates.append(float(llm["repair_rate"]))
        llm_repair = coord.get("llm_repair") or {}
        if llm_repair.get("repair_success_rate") is not None:
            repair_rates.append(float(llm_repair["repair_success_rate"]))
        if llm.get("tokens_per_step") is not None:
            tokens_per_step_list.append(float(llm["tokens_per_step"]))
        elif llm.get("tokens_in") is not None or llm.get("tokens_out") is not None:
            ti = int(llm.get("tokens_in") or 0)
            to = int(llm.get("tokens_out") or 0)
            steps = max(1, m.get("steps") or ep.get("steps") or 1)
            tokens_per_step_list.append((ti + to) / steps)
        if llm.get("latency_ms_list"):
            for v in llm["latency_ms_list"]:
                if v is not None:
                    llm_latency_ms_list.append(float(v))
        elif llm.get("latency_ms") is not None:
            llm_latency_ms_list.append(float(llm["latency_ms"]))
        cost_total_tokens_list.append(int(llm.get("total_tokens") or 0))
        if llm.get("estimated_cost_usd") is not None:
            try:
                cost_estimated_usd_list.append(float(llm["estimated_cost_usd"]))
            except (TypeError, ValueError):
                pass
        if llm.get("error_rate") is not None:
            llm_error_rates.append(float(llm["error_rate"]))
        if llm.get("invalid_output_rate") is not None:
            llm_invalid_output_rates.append(float(llm["invalid_output_rate"]))

    p95_vals = [x for x in p95_list if x is not None]
    det_vals = [x for x in detection_steps if x is not None]
    cont_vals = [x for x in containment_steps if x is not None]
    attr_vals = [x for x in time_to_attribution_list if x is not None]
    blast_vals = [x for x in blast_radius_list if x is not None]
    res_vals = [x for x in resilience_list if x is not None]
    drop_vals = [x for x in drop_rates if x is not None]
    p95_lat_vals = [x for x in p95_latency_ms_list if x is not None]
    partition_vals = [x for x in partition_events_list if x is not None]
    stale_vals = [x for x in stale_rates if x is not None]
    deadlock_vals = [x for x in deadlock_avoids_list if x is not None]
    tok_vals = [x for x in tokens_per_step_list if x is not None]
    llm_lat_vals = [x for x in llm_latency_ms_list if x is not None]

    def _p95(vals: list[float]) -> float | None:
        if not vals:
            return None
        s = sorted(vals)
        k = (len(s) - 1) * 0.95
        lo = int(k)
        hi = min(lo + 1, len(s) - 1)
        return s[lo] + (k - lo) * (s[hi] - s[lo])

    out = {
        "perf.throughput": sum(throughputs) / n if n else 0.0,
        "perf.p95_tat": sum(p95_vals) / len(p95_vals) if p95_vals else None,
        "safety.violations_total": violations_total,
        "safety.blocks_total": blocks_total,
        "sec.attack_success_rate": attack_success_sum / n if n else None,
        "sec.attack_success_rate_ci_lower": (
            clopper_pearson_ci(int(attack_success_sum), n, 0.95)[0] if n >= 1 else None
        ),
        "sec.attack_success_rate_ci_upper": (
            clopper_pearson_ci(int(attack_success_sum), n, 0.95)[1] if n >= 1 else None
        ),
        "sec.worst_case_attack_success_upper_95": (
            worst_case_success_rate_upper(n, 0.95) if n >= 1 and attack_success_sum == 0 else None
        ),
        "sec.attack_success_observed": attack_success_observed_sum / n if n else None,
        "sec.detection_latency_steps": (sum(det_vals) / len(det_vals) if det_vals else None),
        "sec.containment_time_steps": (sum(cont_vals) / len(cont_vals) if cont_vals else None),
        "sec.stealth_success_rate": stealth_success_sum / n if n else None,
        "sec.time_to_attribution_steps": (sum(attr_vals) / len(attr_vals) if attr_vals else None),
        "sec.blast_radius_proxy": (sum(blast_vals) / len(blast_vals) if blast_vals else None),
        "robustness.resilience_score": (sum(res_vals) / len(res_vals) if res_vals else None),
        "comm.msg_count": sum(msg_counts) / len(msg_counts) if msg_counts else None,
        "comm.p95_latency_ms": (sum(p95_lat_vals) / len(p95_lat_vals) if p95_lat_vals else None),
        "comm.drop_rate": sum(drop_vals) / len(drop_vals) if drop_vals else None,
        "comm.partition_events": (sum(partition_vals) if partition_vals else None),
        "coordination.stale_action_rate": (sum(stale_vals) / len(stale_vals) if stale_vals else None),
        "coordination.deadlock_avoids": (sum(deadlock_vals) / len(deadlock_vals) if deadlock_vals else None),
        "proposal_valid_rate": (
            sum(proposal_valid_rates) / len(proposal_valid_rates) if proposal_valid_rates else None
        ),
        "blocked_rate": (sum(blocked_rates) / len(blocked_rates) if blocked_rates else None),
        "repair_rate": (sum(repair_rates) / len(repair_rates) if repair_rates else None),
        "tokens_per_step": (sum(tok_vals) / len(tok_vals) if tok_vals else None),
        "p95_llm_latency_ms": _p95(llm_lat_vals),
        "cost.total_tokens": sum(cost_total_tokens_list),
        "cost.estimated_cost_usd": (sum(cost_estimated_usd_list) if cost_estimated_usd_list else None),
        "llm.error_rate": (sum(llm_error_rates) / len(llm_error_rates) if llm_error_rates else 0.0),
        "llm.invalid_output_rate": (
            sum(llm_invalid_output_rates) / len(llm_invalid_output_rates) if llm_invalid_output_rates else None
        ),
    }
    return out


def _canonical_results_fingerprint(results: dict[str, Any]) -> str:
    """Stable fingerprint for determinism: seeds, episode count, throughputs, violations."""
    episodes = results.get("episodes") or []
    parts = [
        json.dumps(results.get("seeds") or [], sort_keys=True),
        str(len(episodes)),
    ]
    for ep in episodes:
        m = ep.get("metrics") or {}
        parts.append(str(m.get("throughput", 0)))
        vbi = m.get("violations_by_invariant_id") or {}
        parts.append(str(sum(vbi.values()) if isinstance(vbi, dict) else 0))
    payload = "\n".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _enrich_cell_results_with_llm_metadata(
    results: dict[str, Any],
    method_id: str,
    llm_backend: str | None,
    llm_model: str | None,
    agg: dict[str, Any],
    enforce_determinism: bool,
) -> None:
    """Mutate results: set metadata.llm_* from params and aggregated metrics; add results_hash when deterministic."""
    if method_id not in LLM_METHOD_IDS:
        return
    meta = results.get("metadata")
    if meta is None:
        results["metadata"] = meta = {}
    meta["llm_backend"] = llm_backend or "deterministic"
    meta["llm_model"] = llm_model
    meta["llm_method_id"] = method_id
    if agg.get("proposal_valid_rate") is not None:
        meta["llm_proposal_valid_rate"] = agg["proposal_valid_rate"]
    if agg.get("blocked_rate") is not None:
        meta["llm_blocked_rate"] = agg["blocked_rate"]
    if agg.get("repair_rate") is not None:
        meta["llm_repair_rate"] = agg["repair_rate"]
    if agg.get("tokens_per_step") is not None:
        meta["llm_tokens_per_step"] = agg["tokens_per_step"]
    if agg.get("p95_llm_latency_ms") is not None:
        meta["llm_p95_latency_ms"] = agg["p95_llm_latency_ms"]
    if enforce_determinism:
        results["metadata"]["results_hash"] = _canonical_results_fingerprint(results)


def _pareto_dominates(
    a: dict[str, Any],
    b: dict[str, Any],
    objectives: list[tuple[str, str]],
) -> bool:
    """
    True if a dominates b: for each objective (key, direction), a is no worse;
    at least one strictly better. direction "min" => lower better, "max" => higher better.
    """
    at_least_one_better = False
    for key, direction in objectives:
        va = a.get(key)
        vb = b.get(key)
        if va is None or vb is None:
            continue
        if direction == "min":
            if va > vb:
                return False
            if va < vb:
                at_least_one_better = True
        else:
            if va < vb:
                return False
            if va > vb:
                at_least_one_better = True
    return at_least_one_better


def _pareto_front(rows: list[dict[str, Any]], objectives: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Return rows that are on the Pareto front (non-dominated)."""
    front = []
    for r in rows:
        dominated = False
        for other in rows:
            if other is r:
                continue
            if _pareto_dominates(other, r, objectives):
                dominated = True
                break
        if not dominated:
            front.append(r)
    return front


def _write_summary_csv(out_path: Path, rows: list[dict[str, Any]]) -> None:
    """Write summary_coord.csv with required columns including resilience.component_* and optional LLM columns."""
    columns = [
        "method_id",
        "scale_id",
        "risk_id",
        "injection_id",
        "perf.throughput",
        "perf.p95_tat",
        "safety.violations_total",
        "safety.blocks_total",
        "sec.attack_success_rate",
        "sec.attack_success_rate_ci_lower",
        "sec.attack_success_rate_ci_upper",
        "sec.worst_case_attack_success_upper_95",
        "sec.detection_latency_steps",
        "sec.containment_time_steps",
        "sec.stealth_success_rate",
        "sec.time_to_attribution_steps",
        "sec.blast_radius_proxy",
        "robustness.resilience_score",
        "resilience.component_perf",
        "resilience.component_safety",
        "resilience.component_security",
        "resilience.component_coordination",
        "comm.msg_count",
        "comm.p95_latency_ms",
        "comm.drop_rate",
        "comm.partition_events",
        "coordination.stale_action_rate",
        "proposal_valid_rate",
        "blocked_rate",
        "repair_rate",
        "tokens_per_step",
        "p95_llm_latency_ms",
        "cost.total_tokens",
        "cost.estimated_cost_usd",
        "llm.error_rate",
        "llm.invalid_output_rate",
    ]
    optional_empty = [
        "perf.p95_tat",
        "sec.attack_success_rate",
        "sec.attack_success_rate_ci_lower",
        "sec.attack_success_rate_ci_upper",
        "sec.worst_case_attack_success_upper_95",
        "sec.detection_latency_steps",
        "sec.containment_time_steps",
        "sec.stealth_success_rate",
        "sec.time_to_attribution_steps",
        "sec.blast_radius_proxy",
        "robustness.resilience_score",
        "resilience.component_perf",
        "resilience.component_safety",
        "resilience.component_security",
        "resilience.component_coordination",
        "comm.msg_count",
        "comm.p95_latency_ms",
        "comm.drop_rate",
        "comm.partition_events",
        "coordination.stale_action_rate",
        "proposal_valid_rate",
        "blocked_rate",
        "repair_rate",
        "tokens_per_step",
        "p95_llm_latency_ms",
        "cost.total_tokens",
        "cost.estimated_cost_usd",
        "llm.error_rate",
        "llm.invalid_output_rate",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            row = {k: r.get(k) for k in columns}
            for k in optional_empty:
                if row.get(k) is None:
                    row[k] = ""
            w.writerow(row)


def _write_pareto_md(
    out_path: Path,
    summary_rows: list[dict[str, Any]],
    spec: dict[str, Any],
) -> None:
    """
    Write pareto.md: per-scale Pareto front (min p95_tat, min violations, max resilience),
    top 3 methods per scale by resilience, component radar text table, and robust winner.
    """
    objectives = [
        ("perf.p95_tat", "min"),
        ("safety.violations_total", "min"),
        ("robustness.resilience_score", "max"),
    ]
    scale_ids = sorted({r["scale_id"] for r in summary_rows})
    lines = [
        "# Pareto front report (coordination study)",
        "",
        "Objectives: minimize p95_tat, minimize violations_total, maximize resilience_score.",
        "",
        "## Per-scale Pareto front",
        "",
    ]
    for scale_id in scale_ids:
        subset = [r for r in summary_rows if r["scale_id"] == scale_id]
        front = _pareto_front(subset, objectives)
        lines.append(f"### Scale: {scale_id}")
        lines.append("")
        if not front:
            lines.append("(no non-dominated cells)")
        else:
            for r in front:
                method = r.get("method_id", "")
                inj = r.get("injection_id", "")
                p95 = r.get("perf.p95_tat")
                viol = r.get("safety.violations_total", 0)
                res = r.get("robustness.resilience_score")
                p95_s = f"{p95:.1f}" if p95 is not None else "—"
                res_s = f"{res:.3f}" if res is not None else "—"
                lines.append(f"- **{method}** / {inj}: p95_tat={p95_s}, violations={viol}, resilience={res_s}")
        lines.append("")

    # Top 3 methods per scale by mean resilience (across injections for that scale)
    lines.append("## Top 3 methods per scale by resilience")
    lines.append("")
    for scale_id in scale_ids:
        subset = [r for r in summary_rows if r["scale_id"] == scale_id]
        method_scores_local: dict[str, list[float]] = {}
        for r in subset:
            mid = r.get("method_id", "")
            res = r.get("robustness.resilience_score")
            if res is not None and mid:
                method_scores_local.setdefault(mid, []).append(res)
        mean_by_method = {mid: sum(s) / len(s) for mid, s in method_scores_local.items() if s}
        top3 = sorted(
            mean_by_method.items(),
            key=lambda x: -x[1],
        )[:3]
        lines.append(f"### Scale: {scale_id}")
        lines.append("")
        if not top3:
            lines.append("(no resilience scores)")
        else:
            for rank, (mid, score) in enumerate(top3, 1):
                lines.append(f"{rank}. **{mid}** (mean resilience = {score:.3f})")
        lines.append("")

    # Component radar text table: one row per method (aggregate across scales/injections), columns perf, safety, security, coordination
    lines.append("## Component radar (mean component scores by method)")
    lines.append("")
    method_components: dict[str, list[dict[str, Any]]] = {}
    for r in summary_rows:
        mid = r.get("method_id", "")
        if not mid:
            continue
        comp = {
            "perf": r.get("resilience.component_perf"),
            "safety": r.get("resilience.component_safety"),
            "security": r.get("resilience.component_security"),
            "coordination": r.get("resilience.component_coordination"),
        }
        if any(v is not None for v in comp.values()):
            method_components.setdefault(mid, []).append(comp)
    if method_components:
        col_headers = ["method_id", "perf", "safety", "security", "coordination"]
        lines.append("| " + " | ".join(col_headers) + " |")
        lines.append("| " + " | ".join(["---"] * len(col_headers)) + " |")
        for mid in sorted(method_components.keys()):
            comps = method_components[mid]
            mean_perf = _mean_opt([c.get("perf") for c in comps])
            mean_safety = _mean_opt([c.get("safety") for c in comps])
            mean_sec = _mean_opt([c.get("security") for c in comps])
            mean_coord = _mean_opt([c.get("coordination") for c in comps])
            cells = [
                mid,
                f"{mean_perf:.3f}" if mean_perf is not None else "—",
                f"{mean_safety:.3f}" if mean_safety is not None else "—",
                f"{mean_sec:.3f}" if mean_sec is not None else "—",
                f"{mean_coord:.3f}" if mean_coord is not None else "—",
            ]
            lines.append("| " + " | ".join(cells) + " |")
    else:
        lines.append("(no component data)")
    lines.append("")

    # Robust winner: argmax mean resilience across injections (with optional constraints)
    lines.append("## Robust winner under risk suite")
    lines.append("")
    method_scores: dict[str, list[float | None]] = {}
    for r in summary_rows:
        mid = r.get("method_id", "")
        if mid not in method_scores:
            method_scores[mid] = []
        method_scores[mid].append(r.get("robustness.resilience_score"))
    mean_resilience: dict[str, float] = {}
    for mid, scores in method_scores.items():
        vals = [s for s in scores if s is not None]
        mean_resilience[mid] = sum(vals) / len(vals) if vals else 0.0
    if mean_resilience:
        winner = max(mean_resilience, key=lambda k: mean_resilience.get(k, 0.0))
        lines.append(
            f"Method with highest mean resilience across all cells: **{winner}** "
            f"(mean resilience = {mean_resilience[winner]:.3f})."
        )
    else:
        lines.append("No resilience scores available.")
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")


def _mean_opt(values: list[float | None]) -> float | None:
    """Return mean of present values, or None if none."""
    present = [v for v in values if v is not None]
    if not present:
        return None
    return sum(present) / len(present)


def run_coordination_study(
    spec_path: Path,
    out_dir: Path,
    repo_root: Path | None = None,
    llm_backend: str | None = None,
    llm_model: str | None = None,
) -> dict[str, Any]:
    """
    Execute coordination study: expand (scale x method x injection), run episodes_per_cell per cell,
    write cells/<cell_id>/results.json, summary/summary_coord.csv, summary/pareto.md.
    Returns manifest-like dict with cell_ids, study_id, seed_base.

    llm_backend: optional "deterministic" | "live". When None, only non-LLM methods from the spec
    are run (backward compatible). When set, all spec methods including LLM methods are run.
    llm_model: optional model id when using live backend (e.g. gpt-4o).
    """
    repo_root = repo_root or Path.cwd()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    spec = load_coordination_study_spec(spec_path)
    study_id = spec.get("study_id", "coordination_study")
    seed_base = int(spec.get("seed_base", 42))
    episodes_per_cell = int(spec.get("episodes_per_cell", 2))
    smoke = os.environ.get("LABTRUST_REPRO_SMOKE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if smoke:
        episodes_per_cell = min(episodes_per_cell, 1)

    scale_rows = _expand_scale_rows(spec, repo_root)
    methods_raw = spec.get("methods") or []
    method_ids_raw: list[str] = []
    for m in methods_raw:
        if isinstance(m, str):
            method_ids_raw.append(m)
        elif isinstance(m, dict):
            method_ids_raw.append(m.get("method_id") or m.get("method") or "")
        else:
            method_ids_raw.append(str(m))
    method_ids_raw = [x for x in method_ids_raw if x]
    if not method_ids_raw:
        method_ids_raw = ["centralized_planner"]
    # When llm_backend is not set, exclude LLM methods so existing behavior is unchanged.
    if llm_backend is None or llm_backend == "":
        method_ids = [m for m in method_ids_raw if m not in LLM_METHOD_IDS]
    else:
        method_ids = list(method_ids_raw)
    if not method_ids:
        method_ids = ["centralized_planner"]

    injections = _expand_injections(spec)
    risks = spec.get("risks") or []
    map_path = repo_root / "policy" / "coordination" / "risk_to_injection_map.v0.1.yaml"
    inj_to_risk_ids = injection_id_to_risk_ids_map(map_path) if map_path.is_file() else {}
    # Fallback: single risk_id per injection (spec.risks by index or injection_id)
    risk_id_by_injection: dict[str, str] = {}
    for i, inj in enumerate(injections):
        inj_id = inj.get("injection_id", "")
        rids = inj_to_risk_ids.get(inj_id)
        risk_id_by_injection[inj_id] = rids[0] if rids else (risks[i] if i < len(risks) else None) or inj_id

    cells_dir = out_dir / "cells"
    summary_dir = out_dir / "summary"
    cells_dir.mkdir(parents=True, exist_ok=True)
    summary_dir.mkdir(parents=True, exist_ok=True)

    _coverage_preflight(spec, repo_root, summary_dir, injections)

    resilience_policy: dict[str, Any] | None = None
    try:
        resilience_policy = load_resilience_scoring_policy(
            repo_root / "policy" / "coordination" / "resilience_scoring.v0.1.yaml"
        )
    except Exception:
        pass
    if resilience_policy is None:
        resilience_policy = {
            "weights": {
                "perf": 0.25,
                "safety": 0.25,
                "security": 0.25,
                "coordination": 0.25,
            },
            "missing_metric_behavior": "omit",
            "components": {},
        }

    cell_ids: list[str] = []
    summary_rows: list[dict[str, Any]] = []

    for scale_idx, (scale_id, _scale_row, scale_config) in enumerate(scale_rows):
        for method_idx, method_id in enumerate(method_ids):
            for inj_idx, inj_cfg in enumerate(injections):
                injection_id = inj_cfg.get("injection_id", "")
                cell_id = f"{scale_id}_{method_id}_{injection_id}".replace(" ", "_")
                cell_ids.append(cell_id)

                cell_seed = _cell_seed(seed_base, scale_idx, method_idx, inj_idx)
                cell_out = cells_dir / cell_id
                cell_out.mkdir(parents=True, exist_ok=True)
                results_path = cell_out / "results.json"
                log_path = cell_out / "episodes.jsonl"

                run_benchmark(
                    task_name="coord_risk",
                    num_episodes=episodes_per_cell,
                    base_seed=cell_seed,
                    out_path=results_path,
                    repo_root=repo_root,
                    log_path=log_path,
                    coord_method=method_id,
                    injection_id=injection_id,
                    scale_config_override=scale_config,
                    llm_backend=llm_backend,
                    llm_model=llm_model,
                )

                results = json.loads(results_path.read_text(encoding="utf-8"))
                # Optional coordination/security blocks (non-breaking)
                results["coordination"] = {"scale_id": scale_id, "method_id": method_id}
                results["security"] = {
                    "risk_id": risk_id_by_injection.get(injection_id, injection_id),
                    "injection_id": injection_id,
                }
                agg = _aggregate_cell_metrics(results.get("episodes") or [])
                _enrich_cell_results_with_llm_metadata(
                    results,
                    method_id=method_id,
                    llm_backend=llm_backend,
                    llm_model=llm_model,
                    agg=agg,
                    enforce_determinism=(llm_backend == "deterministic"),
                )
                with results_path.open("w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2)

                components = compute_components(agg, resilience_policy)
                resilience_score = compute_resilience_score(components, resilience_policy.get("weights") or {})
                risk_ids_for_cell = inj_to_risk_ids.get(
                    injection_id,
                    [risk_id_by_injection.get(injection_id, injection_id)],
                )
                for rid in sorted(risk_ids_for_cell):
                    row = {
                        "method_id": method_id,
                        "scale_id": scale_id,
                        "risk_id": rid,
                        "injection_id": injection_id,
                        **agg,
                        "robustness.resilience_score": resilience_score,
                        "resilience.component_perf": components.get("component_perf"),
                        "resilience.component_safety": components.get("component_safety"),
                        "resilience.component_security": components.get("component_security"),
                        "resilience.component_coordination": components.get("component_coordination"),
                    }
                    summary_rows.append(row)

    _write_summary_csv(summary_dir / "summary_coord.csv", summary_rows)
    _write_pareto_md(summary_dir / "pareto.md", summary_rows, spec)

    try:
        from labtrust_gym.studies.coordination_summarizer import (
            build_method_class_comparison,
            build_sota_leaderboard,
            write_leaderboard_csv,
            write_leaderboard_md,
            write_method_class_csv,
            write_method_class_md,
        )

        registry = None
        if repo_root and (repo_root / "policy" / "coordination" / "coordination_methods.v0.1.yaml").is_file():
            try:
                from labtrust_gym.policy.coordination import load_coordination_methods

                registry = load_coordination_methods(
                    repo_root / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
                )
            except Exception:
                pass
        leaderboard = build_sota_leaderboard(summary_rows)
        comparison = build_method_class_comparison(summary_rows, registry)
        write_leaderboard_csv(summary_dir / "sota_leaderboard.csv", leaderboard)
        write_leaderboard_md(summary_dir / "sota_leaderboard.md", leaderboard)
        write_method_class_csv(summary_dir / "method_class_comparison.csv", comparison)
        write_method_class_md(summary_dir / "method_class_comparison.md", comparison)
    except Exception:
        pass

    pareto_dir = out_dir / "PARETO"
    try:
        from labtrust_gym.benchmarks.pareto import write_pareto_artifacts

        write_pareto_artifacts(
            pareto_dir,
            summary_rows,
            seed_base,
            spec=spec,
        )
    except Exception:
        pass

    manifest = {
        "study_id": study_id,
        "spec_path": str(spec_path.resolve()),
        "out_dir": str(out_dir.resolve()),
        "seed_base": seed_base,
        "episodes_per_cell": episodes_per_cell,
        "num_cells": len(cell_ids),
        "cell_ids": cell_ids,
    }
    if pareto_dir.exists():
        manifest["pareto_dir"] = str(pareto_dir.resolve())
    manifest_path = out_dir / "manifest_coordination.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest
