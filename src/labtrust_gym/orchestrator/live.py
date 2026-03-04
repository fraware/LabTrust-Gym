"""
Live orchestrator: run chosen coordination method in llm_live, emit same audit/evidence
artifacts, enforce RBAC/signatures/tool sandbox/memory policy, support safe
degradation (fallback baseline) without tearing the system. Produces standard run dir
with matrix + decision + receipts + evidence bundle.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from labtrust_gym.orchestrator.config import OrchestratorConfig
from labtrust_gym.orchestrator.defense import DefenseController, DefenseState


def _cell_id(config: OrchestratorConfig) -> str:
    """Standard cell id for live run: live_<scale>_<method>_<injection>."""
    inj = (config.injection_id or "none").replace("-", "_")
    return f"live_{config.scale_id}_{config.chosen_method_id}_{inj}".replace(" ", "_")


def _extract_defense_transition(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Build defense_transition from episode metrics (sec.detection_latency_steps, containment_time_steps)."""
    out: dict[str, Any] = {
        "attack_detected": False,
        "detection_step": None,
        "containment_step": None,
        "fallback_activated": False,
    }
    for ep in episodes or []:
        m = ep.get("metrics") or {}
        sec = m.get("sec") or {}
        det = sec.get("detection_latency_steps")
        cont = sec.get("containment_time_steps")
        if det is not None:
            out["attack_detected"] = True
            out["detection_step"] = det
        if cont is not None:
            out["containment_step"] = cont
    return out


def run_live_orchestrator(config: OrchestratorConfig) -> dict[str, Any]:
    """
    Run the chosen coordination method in llm_live (or deterministic if no live backend),
    write standard run dir: cells/<cell_id>/results.json, episodes.jsonl, summary/summary_coord.csv,
    defense_transition.json, then export receipts and decision artifact so a reviewer can
    verify via verify-bundle + matrix schema validation.
    """
    from labtrust_gym.benchmarks.coordination_scale import load_scale_config_by_id
    from labtrust_gym.benchmarks.runner import run_benchmark
    from labtrust_gym.studies.coordination_study_runner import _aggregate_cell_metrics

    run_dir = Path(config.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    policy_root = Path(config.policy_root).resolve()
    cell_id = _cell_id(config)
    cell_dir = run_dir / "cells" / cell_id
    cell_dir.mkdir(parents=True, exist_ok=True)
    results_path = cell_dir / "results.json"
    log_path = cell_dir / "episodes.jsonl"

    scale_config = load_scale_config_by_id(policy_root, config.scale_id)
    pipeline_mode = "llm_live" if config.allow_network and (config.llm_backend or "").endswith("_live") else None
    allow_network = config.allow_network

    run_benchmark(
        task_name="coord_risk",
        num_episodes=config.num_episodes,
        base_seed=config.base_seed,
        out_path=results_path,
        repo_root=policy_root,
        log_path=log_path,
        coord_method=config.chosen_method_id,
        injection_id=config.injection_id or None,
        scale_config_override=scale_config,
        llm_backend=config.llm_backend or "deterministic",
        llm_model=config.llm_model,
        pipeline_mode=pipeline_mode,
        allow_network=allow_network,
    )

    with results_path.open("r", encoding="utf-8") as f:
        results = json.load(f)
    episodes = results.get("episodes") or []
    defense_transition = _extract_defense_transition(episodes)
    defense_controller = DefenseController(human_override_token=config.human_override_token)
    if config.defense_enabled and defense_transition.get("attack_detected"):
        defense_controller.state = DefenseState.CONTAINED
        defense_controller.transition_log.append(
            {
                "event": "attack_detected",
                "detection_step": defense_transition.get("detection_step"),
                "containment_step": defense_transition.get("containment_step"),
            }
        )
    defense_path = cell_dir / "defense_transition.json"
    defense_path.write_text(
        json.dumps(
            {
                **defense_transition,
                "defense_state": defense_controller.state.value,
                "transition_log": defense_controller.transition_log,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    summary_dir = run_dir / "summary"
    summary_dir.mkdir(parents=True, exist_ok=True)
    agg = _aggregate_cell_metrics(episodes)
    summary_row = {
        "method_id": config.chosen_method_id,
        "scale_id": config.scale_id,
        "risk_id": config.injection_id or "",
        "injection_id": config.injection_id or "none",
        **{k: v for k, v in agg.items() if k.startswith("perf.") or k.startswith("safety.") or k.startswith("sec.")},
    }
    summary_csv = summary_dir / "summary_coord.csv"
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
        "sec.detection_latency_steps",
        "sec.containment_time_steps",
    ]
    with summary_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        w.writerow({k: summary_row.get(k, "") for k in columns})

    metadata_path = run_dir / "metadata.json"
    metadata = {
        "pipeline_mode": results.get("pipeline_mode", "llm_live"),
        "allow_network": results.get("allow_network", False),
        "task": "coord_risk",
        "cell_id": cell_id,
        "chosen_method_id": config.chosen_method_id,
        "scale_id": config.scale_id,
        "injection_id": config.injection_id or "none",
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    receipts_out = run_dir / "receipts"
    try:
        from labtrust_gym.export.receipts import export_receipts

        export_receipts(
            run_path=log_path,
            out_dir=receipts_out,
            repo_root=policy_root,
            partner_id=(config.extra or {}).get("partner_id"),
        )
    except Exception:
        receipts_out.mkdir(parents=True, exist_ok=True)
        (receipts_out / "export_skipped.txt").write_text(
            "Export receipts skipped (episode log format or dependency unavailable).",
            encoding="utf-8",
        )

    decision_out = run_dir / "decision"
    decision_out.mkdir(parents=True, exist_ok=True)
    try:
        from labtrust_gym.studies.coordination_decision_builder import (
            build_decision,
            write_decision_artifact,
        )

        decision = build_decision(run_dir, policy_root)
        write_decision_artifact(decision, decision_out, policy_root)
        for name in ("COORDINATION_DECISION.v0.1.json", "COORDINATION_DECISION.md"):
            src = decision_out / name
            if src.exists():
                (run_dir / name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    except Exception:
        (decision_out / "decision_skipped.txt").write_text(
            "Decision builder skipped (summary or policy unavailable).",
            encoding="utf-8",
        )

    return {
        "run_dir": str(run_dir),
        "cell_id": cell_id,
        "results_path": str(results_path),
        "summary_path": str(summary_csv),
        "defense_transition": defense_transition,
        "defense_state": defense_controller.state.value,
    }
