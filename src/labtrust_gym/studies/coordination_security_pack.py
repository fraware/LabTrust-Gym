"""
Internal coordination security regression pack: configurable (scale x method x injection)
matrix, deterministic only, 1 episode per cell. Writes pack_results/,
pack_summary.csv, pack_gate.md.

Matrix can be fixed (default from coordination_security_pack.v0.1.yaml), full (all
methods from policy), or from a custom list. Injections can be default, critical,
or policy (all injection_ids from injections.v0.2 that exist in INJECTION_REGISTRY).
Gate thresholds are policy-driven (coordination_security_pack_gate.v0.1.yaml).
"""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any

from labtrust_gym.benchmarks.coordination_scale import (
    load_scale_config_by_id,
)
from labtrust_gym.benchmarks.runner import run_benchmark
from labtrust_gym.policy.gate_eval import (
    evaluate_gate as _evaluate_gate,
)
from labtrust_gym.policy.gate_eval import (
    load_gate_policy as _load_gate_policy,
)
from labtrust_gym.policy.loader import load_yaml
from labtrust_gym.studies.coordination_study_runner import (
    _aggregate_cell_metrics,
)

# Default fixed matrix (backward compatible when config missing)
PACK_SCALES = ["small_smoke", "medium_stress_signed_bus"]
PACK_METHODS = [
    "kernel_auction_whca_shielded",
    "llm_repair_over_kernel_whca",
    "llm_local_decider_signed_bus",
]
PACK_INJECTIONS = [
    "none",
    "INJ-ID-SPOOF-001",
    "INJ-COMMS-POISON-001",
    "INJ-COORD-PROMPT-INJECT-001",
    "INJ-CONSENSUS-POISON-001",
    "INJ-TIMING-QUEUE-001",
]
PACK_EPISODES_PER_CELL = 1
PACK_LLM_BACKEND = "deterministic"

# Subset of summary_coord columns for pack_summary.csv (include security metrics for gate and aggregation)
# application_phase is optional; written when injections.v0.2 or run use non-full phase.
PACK_SUMMARY_COLUMNS = [
    "method_id",
    "scale_id",
    "injection_id",
    "application_phase",
    "perf.throughput",
    "safety.violations_total",
    "safety.blocks_total",
    "sec.attack_success_rate",
    "sec.attack_success_rate_ci_lower",
    "sec.attack_success_rate_ci_upper",
    "sec.worst_case_attack_success_upper_95",
    "sec.attack_success_observed",
    "sec.detection_latency_steps",
    "sec.containment_time_steps",
    "sec.stealth_success_rate",
    "sec.time_to_attribution_steps",
]


def _load_pack_config(repo_root: Path) -> dict[str, Any]:
    """Load coordination_security_pack.v0.1.yaml; return empty dict if missing."""
    path = repo_root / "policy" / "coordination" / "coordination_security_pack.v0.1.yaml"
    if not path.is_file():
        return {}
    return load_yaml(path)


def _get_injection_ids_from_policy_and_registry(repo_root: Path) -> list[str]:
    """Injection IDs from injections.v0.2 that exist in INJECTION_REGISTRY (implemented only); 'none' first."""
    from labtrust_gym.security.risk_injections import (
        INJECTION_REGISTRY,
        is_reserved_injection,
    )

    path = repo_root / "policy" / "coordination" / "injections.v0.2.yaml"
    if not path.is_file():
        all_ids = ["none"] + sorted(INJECTION_REGISTRY.keys())
        return [i for i in all_ids if i == "none" or not is_reserved_injection(i)]
    data = load_yaml(path)
    injections = data.get("injections") or []
    policy_ids = [inj.get("injection_id") for inj in injections if isinstance(inj, dict) and inj.get("injection_id")]
    implemented = set(INJECTION_REGISTRY.keys())
    ordered = ["none"] + [i for i in policy_ids if i in implemented]
    # Append any registry ids not in policy (e.g. legacy INJ-*)
    for iid in sorted(implemented):
        if iid not in ordered:
            ordered.append(iid)
    # Exclude reserved (NoOp) IDs so pack runs only real injections when disallow_reserved_injections is true
    return [i for i in ordered if i == "none" or not is_reserved_injection(i)]


def _get_application_phase_by_injection(repo_root: Path) -> dict[str, str]:
    """Injection ID -> application_phase from injections.v0.2; default 'full'."""
    path = repo_root / "policy" / "coordination" / "injections.v0.2.yaml"
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    try:
        data = load_yaml(path)
        for inj in data.get("injections") or []:
            if isinstance(inj, dict) and inj.get("injection_id"):
                iid = inj["injection_id"]
                phase = inj.get("application_phase")
                if phase and isinstance(phase, str):
                    out[iid] = phase
    except Exception:
        pass
    return out


def _resolve_methods(
    repo_root: Path,
    methods_from: str,
    pack_config: dict[str, Any],
) -> list[str]:
    """Resolve method list: fixed (config default), full (canonical list from config or policy), full_llm (LLM-based methods only), or path to file."""
    if methods_from == "full_llm":
        from labtrust_gym.policy.coordination import list_llm_coordination_method_ids

        reg_path = repo_root / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
        if not reg_path.is_file():
            return PACK_METHODS
        return list_llm_coordination_method_ids(reg_path)
    if methods_from == "full":
        full_list = (pack_config.get("method_ids") or {}).get("full")
        if isinstance(full_list, list) and full_list:
            return list(full_list)
        from labtrust_gym.policy.coordination import load_coordination_methods

        reg_path = repo_root / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
        if not reg_path.is_file():
            return PACK_METHODS
        registry = load_coordination_methods(reg_path)
        return [m for m in sorted(registry.keys()) if m not in ("marl_ppo", "group_evolving_study")]
    if methods_from == "fixed" or not methods_from:
        default = (pack_config.get("method_ids") or {}).get("default")
        if isinstance(default, list) and default:
            return list(default)
        return PACK_METHODS
    # Path to file (one method_id per line or YAML list)
    path = Path(methods_from)
    if not path.is_absolute():
        path = repo_root / path
    if not path.is_file():
        return PACK_METHODS
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("---") or ":" in text.split("\n")[0]:
        data = load_yaml(path)
        ids = data if isinstance(data, list) else (data.get("method_ids") or data.get("methods") or [])
        return list(ids) if isinstance(ids, list) else PACK_METHODS
    return [m.strip() for m in text.splitlines() if m.strip()]


def _resolve_injections(
    repo_root: Path,
    injections_from: str,
    pack_config: dict[str, Any],
) -> list[str]:
    """Resolve injection list: fixed (config default), critical (short list), policy (v0.2 + registry), or path."""
    if injections_from == "policy":
        return _get_injection_ids_from_policy_and_registry(repo_root)
    if injections_from == "critical":
        critical = (pack_config.get("injection_ids") or {}).get("critical")
        if isinstance(critical, list) and critical:
            return list(critical)
        return [
            "none",
            "INJ-ID-SPOOF-001",
            "INJ-COMMS-POISON-001",
            "INJ-COORD-PROMPT-INJECT-001",
        ]
    if injections_from == "fixed" or not injections_from:
        default = (pack_config.get("injection_ids") or {}).get("default")
        if isinstance(default, list) and default:
            return list(default)
        return PACK_INJECTIONS
    # Path to file
    path = Path(injections_from)
    if not path.is_absolute():
        path = repo_root / path
    if not path.is_file():
        return PACK_INJECTIONS
    text = path.read_text(encoding="utf-8").strip()
    if text.startswith("---") or ":" in text.split("\n")[0]:
        data = load_yaml(path)
        ids = data if isinstance(data, list) else (data.get("injection_ids") or data.get("injections") or [])
        return list(ids) if isinstance(ids, list) else PACK_INJECTIONS
    return [i.strip() for i in text.splitlines() if i.strip()]


def _resolve_scales(
    repo_root: Path,
    pack_config: dict[str, Any],
    scale_ids_override: list[str] | None = None,
) -> list[str]:
    """Resolve scale list from override, pack config, or default."""
    if scale_ids_override is not None and len(scale_ids_override) > 0:
        return list(scale_ids_override)
    default = (pack_config.get("scale_ids") or {}).get("default")
    if isinstance(default, list) and default:
        return list(default)
    return PACK_SCALES


def _resolve_from_preset(
    repo_root: Path,
    preset_name: str,
    pack_config: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    """
    Resolve scale_ids, method_ids, injection_ids from a matrix preset.
    Returns (scales, methods, injections). Raises KeyError if preset unknown.
    """
    presets = pack_config.get("matrix_presets") or {}
    preset = presets.get(preset_name)
    if not isinstance(preset, dict):
        raise KeyError(f"Unknown or invalid matrix preset: {preset_name}. Known: {list(presets.keys())}")
    scale_ids = preset.get("scale_ids")
    method_ids = preset.get("method_ids")
    injection_ids = preset.get("injection_ids")
    scales = list(scale_ids) if isinstance(scale_ids, list) and scale_ids else _resolve_scales(repo_root, pack_config)
    methods = (
        list(method_ids)
        if isinstance(method_ids, list) and method_ids
        else _resolve_methods(repo_root, "fixed", pack_config)
    )
    if isinstance(injection_ids, list) and injection_ids:
        inj_list = list(injection_ids)
    elif injection_ids == "critical":
        inj_list = (pack_config.get("injection_ids") or {}).get("critical")
        inj_list = (
            list(inj_list)
            if isinstance(inj_list, list)
            else [
                "none",
                "INJ-ID-SPOOF-001",
                "INJ-COMMS-POISON-001",
                "INJ-COORD-PROMPT-INJECT-001",
            ]
        )
    elif injection_ids == "policy":
        inj_list = _get_injection_ids_from_policy_and_registry(repo_root)
    else:
        inj_list = _resolve_injections(repo_root, "fixed", pack_config)
    return (scales, methods, inj_list)


def _cell_seed(seed_base: int, scale_idx: int, method_idx: int, injection_idx: int) -> int:
    """Deterministic cell seed (stable across runs)."""
    return seed_base + scale_idx * 10000 + method_idx * 100 + injection_idx


# Live backends require allow_network=True in run_benchmark (must match runner's _live_backends)
_LIVE_LLM_BACKENDS = (
    "openai_live",
    "openai_responses",
    "ollama_live",
    "anthropic_live",
    "openai_hosted",
)


def _run_one_cell(
    scale_idx: int,
    scale_id: str,
    method_idx: int,
    method_id: str,
    inj_idx: int,
    injection_id: str,
    seed_base: int,
    root_str: str,
    pack_results_dir_str: str,
    partner_id: str | None,
    application_phase: str,
    llm_backend: str = PACK_LLM_BACKEND,
    allow_network: bool = False,
    multi_agentic: bool = False,
) -> dict[str, Any]:
    """
    Run a single pack cell (one scale x method x injection). Used for parallel execution.
    All arguments must be picklable. Returns one summary row dict.
    llm_backend: backend for coordination/agents (default deterministic). Use openai_live etc. to benchmark LLM methods with live API.
    allow_network: must be True when llm_backend is a live backend.
    """
    root = Path(root_str)
    pack_results_dir = Path(pack_results_dir_str)
    scale_config = load_scale_config_by_id(root, scale_id)
    cell_seed = _cell_seed(seed_base, scale_idx, method_idx, inj_idx)
    cell_id = f"{scale_id}_{method_id}_{injection_id}".replace(" ", "_")
    cell_out = pack_results_dir / cell_id
    cell_out.mkdir(parents=True, exist_ok=True)
    results_path = cell_out / "results.json"
    log_path = cell_out / "episodes.jsonl"

    run_benchmark(
        task_name="coord_risk",
        num_episodes=PACK_EPISODES_PER_CELL,
        base_seed=cell_seed,
        out_path=results_path,
        repo_root=root,
        log_path=log_path,
        coord_method=method_id,
        injection_id=injection_id,
        scale_config_override=scale_config,
        llm_backend=llm_backend or PACK_LLM_BACKEND,
        llm_model=None,
        partner_id=partner_id,
        allow_network=allow_network,
        agent_driven=multi_agentic,
        multi_agentic=multi_agentic,
    )

    results = json.loads(results_path.read_text(encoding="utf-8"))
    results.setdefault("coordination", {})["scale_id"] = scale_id
    results.setdefault("coordination", {})["method_id"] = method_id
    results.setdefault("security", {})["injection_id"] = injection_id
    episodes = results.get("episodes") or []
    agg = _aggregate_cell_metrics(episodes)
    with results_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    row: dict[str, Any] = {
        "method_id": method_id,
        "scale_id": scale_id,
        "injection_id": injection_id,
        "application_phase": application_phase,
        **agg,
    }
    return row


def _run_cells_sequential(
    scale_rows: list[tuple[str, Any]],
    methods: list[str],
    injections: list[str],
    seed_base: int,
    root: Path,
    pack_results_dir: Path,
    partner_id: str | None,
    application_phase_by_injection: dict[str, str],
    llm_backend: str = PACK_LLM_BACKEND,
    allow_network: bool = False,
    multi_agentic: bool = False,
) -> list[dict[str, Any]]:
    """Run all cells one after another. scale_rows items are (scale_id, scale_config).
    On per-cell exception, append a minimal row so pack_summary and pack_gate are still written."""
    summary_rows: list[dict[str, Any]] = []
    for scale_idx, (scale_id, scale_config) in enumerate(scale_rows):
        for method_idx, method_id in enumerate(methods):
            for inj_idx, injection_id in enumerate(injections):
                application_phase = application_phase_by_injection.get(injection_id, "full")
                try:
                    row = _run_one_cell(
                        scale_idx=scale_idx,
                        scale_id=scale_id,
                        method_idx=method_idx,
                        method_id=method_id,
                        inj_idx=inj_idx,
                        injection_id=injection_id,
                        seed_base=seed_base,
                        root_str=str(root.resolve()),
                        pack_results_dir_str=str(pack_results_dir.resolve()),
                        partner_id=partner_id,
                        application_phase=application_phase,
                        llm_backend=llm_backend,
                        allow_network=allow_network,
                        multi_agentic=multi_agentic,
                    )
                    summary_rows.append(row)
                except Exception as e:  # noqa: BLE001
                    logging.getLogger(__name__).warning(
                        "Cell %s/%s/%s failed: %s", scale_id, method_id, injection_id, e
                    )
                    summary_rows.append(
                        {
                            "method_id": method_id,
                            "scale_id": scale_id,
                            "injection_id": injection_id,
                            "application_phase": application_phase,
                            "perf.throughput": None,
                            "safety.violations_total": None,
                            "safety.blocks_total": None,
                            "sec.attack_success_rate": None,
                            "sec.attack_success_rate_ci_lower": None,
                            "sec.attack_success_rate_ci_upper": None,
                            "sec.worst_case_attack_success_upper_95": None,
                            "sec.attack_success_observed": None,
                            "sec.detection_latency_steps": None,
                            "sec.containment_time_steps": None,
                            "sec.stealth_success_rate": None,
                            "sec.time_to_attribution_steps": None,
                            "_cell_error": str(e)[:200],
                        }
                    )
    return summary_rows


def _run_cells_parallel(
    scale_rows: list[tuple[str, Any]],
    methods: list[str],
    injections: list[str],
    seed_base: int,
    root_str: str,
    pack_results_dir_str: str,
    partner_id: str | None,
    application_phase_by_injection: dict[str, str],
    workers: int,
    llm_backend: str = PACK_LLM_BACKEND,
    allow_network: bool = False,
    multi_agentic: bool = False,
) -> list[dict[str, Any]]:
    """Run cells in parallel with ProcessPoolExecutor; return rows in matrix order."""
    from concurrent.futures import ProcessPoolExecutor, as_completed

    cell_args: list[tuple[Any, ...]] = []
    for scale_idx, (scale_id, _) in enumerate(scale_rows):
        for method_idx, method_id in enumerate(methods):
            for inj_idx, injection_id in enumerate(injections):
                application_phase = application_phase_by_injection.get(injection_id, "full")
                cell_args.append(
                    (
                        scale_idx,
                        scale_id,
                        method_idx,
                        method_id,
                        inj_idx,
                        injection_id,
                        seed_base,
                        root_str,
                        pack_results_dir_str,
                        partner_id,
                        application_phase,
                        llm_backend,
                        allow_network,
                        multi_agentic,
                    )
                )

    results_by_idx: dict[int, dict[str, Any]] = {}
    with ProcessPoolExecutor(max_workers=workers) as executor:
        future_to_idx = {executor.submit(_run_one_cell, *args): i for i, args in enumerate(cell_args)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results_by_idx[idx] = future.result()
            except Exception as e:
                scale_id = cell_args[idx][1]
                method_id = cell_args[idx][3]
                injection_id = cell_args[idx][5]
                raise RuntimeError(f"Cell ({scale_id}, {method_id}, {injection_id}) failed: {e}") from e

    return [results_by_idx[i] for i in range(len(cell_args))]


def run_coordination_security_pack(
    out_dir: Path,
    repo_root: Path | None = None,
    seed_base: int = 42,
    methods_from: str = "fixed",
    injections_from: str = "fixed",
    scales_from: str = "default",
    matrix_preset: str | None = None,
    scale_ids_filter: list[str] | None = None,
    partner_id: str | None = None,
    workers: int = 1,
    llm_backend: str | None = None,
    allow_network: bool = False,
    multi_agentic: bool = False,
) -> None:
    """
    Run the coordination security pack matrix and write pack_results/,
    pack_summary.csv, and pack_gate.md.

    methods_from: "fixed" (config default), "full" (all from policy except marl_ppo), or path.
    injections_from: "fixed" (config default), "critical" (short list), "policy" (v0.2 + registry), or path.
    scales_from: "default" (config default: 2 scales), "full" (all 3 scales from config).
    matrix_preset: when set (e.g. "hospital_lab"), resolve scales, methods, and injections from
        policy matrix_presets.<name>; overrides methods_from, injections_from, scales_from.
    scale_ids_filter: when set, run only these scale_ids (e.g. ["small_smoke"]). Restricts the resolved scale list.
    partner_id: optional partner overlay ID; effective policy merged for each pack cell.
    workers: number of parallel workers (default 1 = sequential). Use >1 to run cells in parallel.
    llm_backend: backend for coordination/agents (default deterministic). Use openai_live, ollama_live, etc.
        to benchmark LLM methods with live API; requires allow_network=True.
    allow_network: when True and llm_backend is live, allows API calls. Required for openai_live, etc.
    multi_agentic: when True, run each cell with agent_driven=True and multi_agentic=True (combine path under attack).
    """
    root = Path(repo_root) if repo_root else Path.cwd()
    out_dir = Path(out_dir)
    pack_config = _load_pack_config(root)
    if matrix_preset:
        scales, methods, injections = _resolve_from_preset(root, matrix_preset, pack_config)
    else:
        methods = _resolve_methods(root, methods_from or "fixed", pack_config)
        injections = _resolve_injections(root, injections_from or "fixed", pack_config)
        scale_ids_override = None
        if (scales_from or "default").strip().lower() == "full":
            full_scales = (pack_config.get("scale_ids") or {}).get("full")
            if isinstance(full_scales, list) and full_scales:
                scale_ids_override = list(full_scales)
        scales = _resolve_scales(root, pack_config, scale_ids_override=scale_ids_override)

    if scale_ids_filter:
        allowed = set(scale_ids_filter)
        before = list(scales)
        scales = [s for s in scales if s in allowed]
        if not scales:
            raise ValueError(
                f"scale_ids_filter {scale_ids_filter} did not match any resolved scale. Resolved scales: {before}"
            )

    disallow_reserved = pack_config.get("disallow_reserved_injections", True)
    if disallow_reserved:
        from labtrust_gym.security.risk_injections import RESERVED_NOOP_INJECTION_IDS

        reserved_in_list = [iid for iid in injections if iid != "none" and iid in RESERVED_NOOP_INJECTION_IDS]
        if reserved_in_list:
            raise ValueError(
                "Reserved injection IDs are not allowed in security pack when "
                "disallow_reserved_injections is true: " + ", ".join(sorted(reserved_in_list))
            )

    pack_results_dir = out_dir / "pack_results"
    pack_results_dir.mkdir(parents=True, exist_ok=True)

    scale_rows: list[tuple[str, Any]] = []
    for scale_id in scales:
        try:
            config = load_scale_config_by_id(root, scale_id)
            scale_rows.append((scale_id, config))
        except (KeyError, FileNotFoundError, ValueError) as e:
            raise ValueError(f"Failed to load scale config '{scale_id}': {e}") from e

    application_phase_by_injection = _get_application_phase_by_injection(root)
    root_str = str(root.resolve())
    pack_results_dir_str = str(pack_results_dir.resolve())

    effective_llm_backend = (llm_backend or PACK_LLM_BACKEND).strip() or PACK_LLM_BACKEND
    effective_allow_network = allow_network or (effective_llm_backend in _LIVE_LLM_BACKENDS)

    if workers <= 1:
        summary_rows = _run_cells_sequential(
            scale_rows,
            methods,
            injections,
            seed_base,
            root,
            pack_results_dir,
            partner_id,
            application_phase_by_injection,
            llm_backend=effective_llm_backend,
            allow_network=effective_allow_network,
            multi_agentic=multi_agentic,
        )
    else:
        summary_rows = _run_cells_parallel(
            scale_rows,
            methods,
            injections,
            seed_base,
            root_str,
            pack_results_dir_str,
            partner_id,
            application_phase_by_injection,
            workers,
            llm_backend=effective_llm_backend,
            allow_network=effective_allow_network,
            multi_agentic=multi_agentic,
        )

    # Nominal: (scale_id, method_id) -> violations_total for injection "none"
    nominal_by_scale_method: dict[tuple[str, str], int] = {}
    for r in summary_rows:
        if (r.get("injection_id") or "").strip() == "none":
            key = (r.get("scale_id") or "", r.get("method_id") or "")
            v = r.get("safety.violations_total")
            try:
                nominal_by_scale_method[key] = int(v) if v is not None else 0
            except (TypeError, ValueError):
                nominal_by_scale_method[key] = 0

    gate_policy = _load_gate_policy(root)

    # pack_summary.csv
    summary_path = out_dir / "pack_summary.csv"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    with summary_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=PACK_SUMMARY_COLUMNS, extrasaction="ignore")
        w.writeheader()
        for r in summary_rows:
            out_row = {k: r.get(k) for k in PACK_SUMMARY_COLUMNS}
            for k in PACK_SUMMARY_COLUMNS:
                if out_row.get(k) is None:
                    out_row[k] = ""
            w.writerow(out_row)

    # pack_gate.md and gate verdicts for summary
    gate_path = out_dir / "pack_gate.md"
    gate_lines = [
        "# Coordination security pack – gate results",
        "",
        "Verdict: PASS (threshold met) | FAIL (threshold violated) | "
        "SKIP (not_applicable | no_data | disabled_by_config) | not_supported.",
        "",
        "| scale_id | method_id | injection_id | verdict | rationale |",
        "|----------|-----------|--------------|---------|-----------|",
    ]
    cell_verdicts: list[dict[str, Any]] = []
    for r in summary_rows:
        verdict, rationale = _evaluate_gate(r, nominal_by_scale_method, gate_policy)
        scale_id = r.get("scale_id", "")
        method_id = r.get("method_id", "")
        inj_id = r.get("injection_id", "")
        gate_lines.append(f"| {scale_id} | {method_id} | {inj_id} | {verdict} | {rationale} |")
        cell_verdicts.append(
            {
                "scale_id": scale_id,
                "method_id": method_id,
                "injection_id": inj_id,
                "verdict": verdict,
                "rationale": rationale,
            }
        )
    gate_lines.append("")
    gate_path.write_text("\n".join(gate_lines), encoding="utf-8")

    # SECURITY/coord_pack_gate_summary.json for security suite runner (machine-readable overall pass)
    security_dir = out_dir / "SECURITY"
    security_dir.mkdir(parents=True, exist_ok=True)
    failed_cells = [c for c in cell_verdicts if c.get("verdict") == "FAIL"]
    passed_count = sum(1 for c in cell_verdicts if c.get("verdict") == "PASS")
    failed_count = len(failed_cells)
    skipped_count = sum(1 for c in cell_verdicts if c.get("verdict") in ("SKIP", "not_supported"))
    gate_summary = {
        "overall_pass": failed_count == 0,
        "total_cells": len(cell_verdicts),
        "passed": passed_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "failed_cells": failed_cells,
    }
    gate_summary_path = security_dir / "coord_pack_gate_summary.json"
    gate_summary_path.write_text(
        json.dumps(gate_summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    # SECURITY/coordination_risk_matrix.csv and .md (single view of method x injection x phase outcomes)
    matrix_columns = [
        "method_id",
        "injection_id",
        "application_phase",
        "scale_id",
        "sec.attack_success_rate",
        "sec.attack_success_rate_ci_lower",
        "sec.attack_success_rate_ci_upper",
        "sec.worst_case_attack_success_upper_95",
        "sec.detection_latency_steps",
        "sec.containment_time_steps",
        "sec.stealth_success_rate",
        "sec.time_to_attribution_steps",
        "verdict",
    ]
    matrix_path = security_dir / "coordination_risk_matrix.csv"
    with matrix_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=matrix_columns, extrasaction="ignore")
        w.writeheader()
        for r in summary_rows:
            verdict, _ = _evaluate_gate(r, nominal_by_scale_method, gate_policy)
            out_row = {k: r.get(k) for k in matrix_columns if k != "verdict"}
            out_row["verdict"] = verdict
            for k in matrix_columns:
                if out_row.get(k) is None:
                    out_row[k] = ""
            w.writerow(out_row)

    # Human-readable coordination_risk_matrix.md (table per method_id or single table)
    md_path = security_dir / "coordination_risk_matrix.md"
    md_lines = [
        "# Coordination risk matrix",
        "",
        "One row per (method_id, injection_id, application_phase, scale_id). "
        "Verdict: PASS | FAIL | SKIP | not_supported.",
        "",
        "| method_id | injection_id | application_phase | scale_id | sec.attack_success_rate | sec.attack_success_rate_ci_lower | sec.attack_success_rate_ci_upper | sec.worst_case_attack_success_upper_95 | sec.detection_latency_steps | sec.containment_time_steps | sec.stealth_success_rate | verdict |",
        "|-----------|---------------|-------------------|----------|--------------------------|----------------------------------|-----------------------------------|----------------------------------------|-----------------------------|-----------------------------|---------------------------|---------|",
    ]
    for r in summary_rows:
        verdict, _ = _evaluate_gate(r, nominal_by_scale_method, gate_policy)
        method_id = r.get("method_id", "")
        injection_id = r.get("injection_id", "")
        application_phase = r.get("application_phase", "full")
        scale_id = r.get("scale_id", "")
        ar = r.get("sec.attack_success_rate", "")
        ar_lo = r.get("sec.attack_success_rate_ci_lower", "")
        ar_hi = r.get("sec.attack_success_rate_ci_upper", "")
        wc = r.get("sec.worst_case_attack_success_upper_95", "")
        dl = r.get("sec.detection_latency_steps", "")
        ct = r.get("sec.containment_time_steps", "")
        ss = r.get("sec.stealth_success_rate", "")
        md_lines.append(
            f"| {method_id} | {injection_id} | {application_phase} | {scale_id} | {ar} | {ar_lo} | {ar_hi} | {wc} | {dl} | {ct} | {ss} | {verdict} |"
        )
    md_lines.append("")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
