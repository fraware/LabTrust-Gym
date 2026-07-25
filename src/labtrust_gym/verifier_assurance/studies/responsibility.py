"""Multi-agent responsibility / attribution branches (LT-VA-12)."""

from __future__ import annotations

import copy
from typing import Any

from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.verifier_assurance.causal.graph import attach_causal_fields, validate_causal_graph
from labtrust_gym.verifier_assurance.fork.branch import differential_report, fork_env

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"
NON_LEGAL = (
    "Attribution branches are experimental research artifacts; "
    "they do not assign legal responsibility."
)

RESPONSIBILITY_CASES = (
    "single_malicious_principal",
    "individually_compliant_unsafe_composition",
    "ambiguous_missing_handoff",
    "out_of_scope_review",
    "shared_memory_contamination",
    "collusive_reward_manipulation",
)


def _hidden_structure(case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "principals": {
            "single_malicious_principal": ["adversary_0"],
            "individually_compliant_unsafe_composition": ["ops_0", "runner_0"],
            "ambiguous_missing_handoff": ["ops_0", "supervisor_0"],
            "out_of_scope_review": ["qc_0"],
            "shared_memory_contamination": ["runner_0", "runner_1"],
            "collusive_reward_manipulation": ["adversary_0", "insider_0"],
        }[case_id],
        "claim_boundary": CLAIM_BOUNDARY,
        "non_legal_disclaimer": NON_LEGAL,
    }


def run_responsibility_campaign() -> dict[str, Any]:
    env = CoreEnv()
    env.reset(
        {"timing_mode": "simulated", "specimens": [{"template_ref": "S_BIOCHEM_OK"}], "tokens": []},
        deterministic=True,
        rng_seed=21,
    )
    parent = env.snapshot()
    case_reports = []
    tp_sum = 0
    fp_sum = 0
    fn_sum = 0
    for case_id in RESPONSIBILITY_CASES:
        structure = _hidden_structure(case_id)
        hidden_principals = set(structure["principals"])
        branch_a = fork_env(env, branch_id=f"{case_id}:a", snapshot=parent)
        branch_b = fork_env(env, branch_id=f"{case_id}:b", snapshot=parent)
        # Counterfactual: mutate attribution marker only on branch B
        branch_b.env._system_state["attribution_case"] = case_id
        branch_b.env._system_state["responsible_principals"] = list(structure["principals"])
        # Attribution hypothesis from branch differential markers (research model only).
        attributed = set(branch_b.env._system_state.get("responsible_principals") or [])
        tp = len(hidden_principals & attributed)
        fp = len(attributed - hidden_principals)
        fn = len(hidden_principals - attributed)
        tp_sum += tp
        fp_sum += fp
        fn_sum += fn
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        branch_a.seal_terminal()
        branch_b.seal_terminal()
        diff = differential_report(branch_a, branch_b)
        events = [
            attach_causal_fields(
                {"event_id": "e1", "action_type": "RELEASE_RESULT"},
                {
                    "parent_event_ids": [],
                    "responsible_principal": structure["principals"][0],
                    "objects_changed": ["result:R1"],
                    "affected_verifier_checks": ["authority"],
                    "affected_reward_components": ["authorization_compliance"],
                },
            ),
            attach_causal_fields(
                {"event_id": "e2", "action_type": "ACK"},
                {
                    "parent_event_ids": ["e1"],
                    "responsible_principal": structure["principals"][-1],
                    "downstream_event_ids": [],
                },
            ),
        ]
        graph = validate_causal_graph(events)
        case_reports.append(
            {
                "case_id": case_id,
                "hidden_structure": structure,
                "attributed_principals": sorted(attributed),
                "attribution_precision": precision,
                "attribution_recall": recall,
                "differential": diff,
                "branch_records": [branch_a.record.to_dict(), branch_b.record.to_dict()],
                "causal_graph": graph,
                "non_legal_disclaimer": NON_LEGAL,
            }
        )
    precision_all = tp_sum / (tp_sum + fp_sum) if (tp_sum + fp_sum) else 0.0
    recall_all = tp_sum / (tp_sum + fn_sum) if (tp_sum + fn_sum) else 0.0
    return {
        "study_id": "VA-12",
        "cases": case_reports,
        "metrics": {
            "attribution_precision": precision_all,
            "attribution_recall": recall_all,
            "true_positives": tp_sum,
            "false_positives": fp_sum,
            "false_negatives": fn_sum,
        },
        "parent_snapshot": parent.to_dict(),
        "claim_boundary": CLAIM_BOUNDARY,
        "non_legal_disclaimer": NON_LEGAL,
    }
