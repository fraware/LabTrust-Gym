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
from pathlib import Path
from typing import Any

from labtrust_gym.benchmarks.coordination_scale import (
    CoordinationScaleConfig,
    load_scale_config_by_id,
)
from labtrust_gym.benchmarks.runner import run_benchmark
from labtrust_gym.policy.gate_eval import (
    SKIP_REASON_DISABLED_BY_CONFIG,
    SKIP_REASON_NO_DATA,
    SKIP_REASON_NOT_APPLICABLE,
    evaluate_gate as _evaluate_gate,
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
    "sec.detection_latency_steps",
    "sec.containment_time_steps",
    "sec.stealth_success_rate",
    "sec.time_to_attribution_steps",
]


def _load_pack_config(repo_root: Path) -> dict[str, Any]:
    """Load coordination_security_pack.v0.1.yaml; return empty dict if missing."""
    path = (
        repo_root / "policy" / "coordination" / "coordination_security_pack.v0.1.yaml"
    )
    if not path.is_file():
        return {}
    return load_yaml(path)


def _get_injection_ids_from_policy_and_registry(repo_root: Path) -> list[str]:
    """Injection IDs from injections.v0.2 that exist in INJECTION_REGISTRY; 'none' first."""
    from labtrust_gym.security.risk_injections import INJECTION_REGISTRY

    path = repo_root / "policy" / "coordination" / "injections.v0.2.yaml"
    if not path.is_file():
        return ["none"] + sorted(INJECTION_REGISTRY.keys())
    data = load_yaml(path)
    injections = data.get("injections") or []
    policy_ids = [
        inj.get("injection_id")
        for inj in injections
        if isinstance(inj, dict) and inj.get("injection_id")
    ]
    implemented = set(INJECTION_REGISTRY.keys())
    ordered = ["none"] + [i for i in policy_ids if i in implemented]
    # Append any registry ids not in policy (e.g. legacy INJ-*)
    for iid in sorted(implemented):
        if iid not in ordered:
            ordered.append(iid)
    return ordered


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
    """Resolve method list: fixed (config default), full (canonical list from config or policy), or path to file."""
    if methods_from == "full":
        full_list = (pack_config.get("method_ids") or {}).get("full")
        if isinstance(full_list, list) and full_list:
            return list(full_list)
        from labtrust_gym.policy.coordination import load_coordination_methods

        reg_path = (
            repo_root / "policy" / "coordination" / "coordination_methods.v0.1.yaml"
        )
        if not reg_path.is_file():
            return PACK_METHODS
        registry = load_coordination_methods(reg_path)
        return [
            m
            for m in sorted(registry.keys())
            if m not in ("marl_ppo", "group_evolving_study")
        ]
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
        ids = (
            data
            if isinstance(data, list)
            else (data.get("method_ids") or data.get("methods") or [])
        )
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
        ids = (
            data
            if isinstance(data, list)
            else (data.get("injection_ids") or data.get("injections") or [])
        )
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
        raise KeyError(
            f"Unknown or invalid matrix preset: {preset_name}. Known: {list(presets.keys())}"
        )
    scale_ids = preset.get("scale_ids")
    method_ids = preset.get("method_ids")
    injection_ids = preset.get("injection_ids")
    scales = (
        list(scale_ids)
        if isinstance(scale_ids, list) and scale_ids
        else _resolve_scales(repo_root, pack_config)
    )
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
    else:
        inj_list = _resolve_injections(repo_root, "fixed", pack_config)
    return (scales, methods, inj_list)


def _cell_seed(
    seed_base: int, scale_idx: int, method_idx: int, injection_idx: int
) -> int:
    """Deterministic cell seed (stable across runs)."""
    return seed_base + scale_idx * 10000 + method_idx * 100 + injection_idx


def run_coordination_security_pack(
    out_dir: Path,
    repo_root: Path | None = None,
    seed_base: int = 42,
    methods_from: str = "fixed",
    injections_from: str = "fixed",
    matrix_preset: str | None = None,
    partner_id: str | None = None,
) -> None:
    """
    Run the coordination security pack matrix and write pack_results/,
    pack_summary.csv, and pack_gate.md. Uses deterministic backend only.

    methods_from: "fixed" (config default), "full" (all from policy except marl_ppo), or path.
    injections_from: "fixed" (config default), "critical" (short list), "policy" (v0.2 + registry), or path.
    matrix_preset: when set (e.g. "hospital_lab"), resolve scales, methods, and injections from
        policy matrix_presets.<name>; overrides methods_from and injections_from.
    partner_id: optional partner overlay ID; effective policy merged for each pack cell.
    """
    root = Path(repo_root) if repo_root else Path.cwd()
    out_dir = Path(out_dir)
    pack_config = _load_pack_config(root)
    if matrix_preset:
        scales, methods, injections = _resolve_from_preset(
            root, matrix_preset, pack_config
        )
    else:
        methods = _resolve_methods(root, methods_from or "fixed", pack_config)
        injections = _resolve_injections(root, injections_from or "fixed", pack_config)
        scales = _resolve_scales(root, pack_config)

    pack_results_dir = out_dir / "pack_results"
    pack_results_dir.mkdir(parents=True, exist_ok=True)

    scale_rows: list[tuple[str, CoordinationScaleConfig]] = []
    for scale_id in scales:
        try:
            config = load_scale_config_by_id(root, scale_id)
            scale_rows.append((scale_id, config))
        except (KeyError, FileNotFoundError, ValueError) as e:
            raise ValueError(f"Failed to load scale config '{scale_id}': {e}") from e

    application_phase_by_injection = _get_application_phase_by_injection(root)
    summary_rows: list[dict[str, Any]] = []
    for scale_idx, (scale_id, scale_config) in enumerate(scale_rows):
        for method_idx, method_id in enumerate(methods):
            for inj_idx, injection_id in enumerate(injections):
                cell_id = f"{scale_id}_{method_id}_{injection_id}".replace(" ", "_")
                cell_seed = _cell_seed(seed_base, scale_idx, method_idx, inj_idx)
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
                    llm_backend=PACK_LLM_BACKEND,
                    llm_model=None,
                    partner_id=partner_id,
                )

                results = json.loads(results_path.read_text(encoding="utf-8"))
                results.setdefault("coordination", {})["scale_id"] = scale_id
                results.setdefault("coordination", {})["method_id"] = method_id
                results.setdefault("security", {})["injection_id"] = injection_id
                episodes = results.get("episodes") or []
                agg = _aggregate_cell_metrics(episodes)
                with results_path.open("w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2)

                application_phase = application_phase_by_injection.get(
                    injection_id, "full"
                )
                row: dict[str, Any] = {
                    "method_id": method_id,
                    "scale_id": scale_id,
                    "injection_id": injection_id,
                    "application_phase": application_phase,
                    **agg,
                }
                summary_rows.append(row)

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

    # pack_gate.md
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
    for r in summary_rows:
        verdict, rationale = _evaluate_gate(r, nominal_by_scale_method, gate_policy)
        scale_id = r.get("scale_id", "")
        method_id = r.get("method_id", "")
        inj_id = r.get("injection_id", "")
        gate_lines.append(
            f"| {scale_id} | {method_id} | {inj_id} | {verdict} | {rationale} |"
        )
    gate_lines.append("")
    gate_path.write_text("\n".join(gate_lines), encoding="utf-8")

    # SECURITY/coordination_risk_matrix.csv and .md (single view of method x injection x phase outcomes)
    security_dir = out_dir / "SECURITY"
    security_dir.mkdir(parents=True, exist_ok=True)
    matrix_columns = [
        "method_id",
        "injection_id",
        "application_phase",
        "scale_id",
        "sec.attack_success_rate",
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
        "| method_id | injection_id | application_phase | scale_id | sec.attack_success_rate | sec.detection_latency_steps | sec.containment_time_steps | sec.stealth_success_rate | verdict |",
        "|-----------|---------------|-------------------|----------|--------------------------|-----------------------------|-----------------------------|---------------------------|---------|",
    ]
    for r in summary_rows:
        verdict, _ = _evaluate_gate(r, nominal_by_scale_method, gate_policy)
        method_id = r.get("method_id", "")
        injection_id = r.get("injection_id", "")
        application_phase = r.get("application_phase", "full")
        scale_id = r.get("scale_id", "")
        ar = r.get("sec.attack_success_rate", "")
        dl = r.get("sec.detection_latency_steps", "")
        ct = r.get("sec.containment_time_steps", "")
        ss = r.get("sec.stealth_success_rate", "")
        md_lines.append(
            f"| {method_id} | {injection_id} | {application_phase} | {scale_id} | {ar} | {dl} | {ct} | {ss} | {verdict} |"
        )
    md_lines.append("")
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
