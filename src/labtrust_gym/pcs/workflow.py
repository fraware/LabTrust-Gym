"""Execute PCS QC-release workflow scenarios from YAML."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from labtrust_gym.pcs.policy import load_qc_release_policy, role_can_release
from labtrust_gym.pcs.trace import TraceBuilder

INITIAL_STATE: dict[str, Any] = {
    "lifecycle": "registered",
    "qc_complete": False,
    "analysis_complete": False,
    "released": False,
}


def _copy_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "lifecycle": state["lifecycle"],
        "qc_complete": state["qc_complete"],
        "analysis_complete": state["analysis_complete"],
        "released": state["released"],
    }


def load_workflow_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def evaluate_action(
    action: str,
    state: dict[str, Any],
    actor_role: str,
    *,
    policy_root: Path | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """
    Return (policy_decision, reason_code, post_state).
    policy_decision is allow or deny; post_state reflects transition on allow only.
    """
    policy = load_qc_release_policy(policy_root)
    transitions = policy.get("transitions", {})
    post = _copy_state(state)

    if action not in transitions:
        return "deny", "invalid_transition", post

    rule = transitions[action]
    required_lifecycle = rule.get("requires_lifecycle")
    if required_lifecycle and state.get("lifecycle") != required_lifecycle:
        if action == "release_sample" and not state.get("qc_complete"):
            return "deny", "missing_qc", post
        return "deny", "invalid_transition", post

    if action == "perform_qc":
        if state.get("lifecycle") != "accessioned":
            return "deny", "invalid_transition", post
        post["qc_complete"] = True
        post["lifecycle"] = "qc_complete"
        return "allow", "ok", post

    if action == "record_analysis":
        if state.get("lifecycle") != "qc_complete":
            return "deny", "invalid_transition", post
        post["analysis_complete"] = True
        post["lifecycle"] = "analyzed"
        return "allow", "ok", post

    if action == "release_sample":
        if not state.get("qc_complete"):
            return "deny", "missing_qc", post
        if state.get("lifecycle") != "analyzed":
            return "deny", "invalid_transition", post
        if not role_can_release(actor_role, policy_root):
            return "deny", "unauthorized_release", post
        post["released"] = True
        post["lifecycle"] = "released"
        return "allow", "ok", post

    if action == "accession_sample":
        if state.get("lifecycle") != "registered":
            return "deny", "invalid_transition", post
        post["lifecycle"] = "accessioned"
        return "allow", "ok", post

    return "deny", "policy_denied", post


def run_workflow(
    workflow: dict[str, Any],
    *,
    run_id: str | None = None,
    policy_root: Path | None = None,
) -> dict[str, Any]:
    """Execute workflow steps; return run result with trace document and metadata."""
    sample_id = str(workflow["sample_id"])
    rid = run_id or str(workflow.get("run_id", f"pcs-{workflow.get('scenario_id', 'run')}"))
    builder = TraceBuilder(run_id=rid, sample_id=sample_id)
    state = _copy_state(INITIAL_STATE)
    final_reason = "ok"
    run_status = "completed"
    released = False

    for idx, step in enumerate(workflow.get("steps", [])):
        action = str(step["action"])
        pre = _copy_state(state)
        decision, reason, post = evaluate_action(
            action,
            state,
            str(step["actor_role"]),
            policy_root=policy_root,
        )
        if decision == "allow":
            state = post
            if action == "release_sample":
                released = True
        else:
            final_reason = reason
            if action == "release_sample":
                run_status = "failed"
                post = _copy_state(state)
            else:
                run_status = "failed"
                post = _copy_state(state)

        builder.append_event(
            event_id=f"{rid}-evt-{idx:03d}",
            timestamp=str(step["timestamp"]),
            actor_id=str(step["actor_id"]),
            actor_role=str(step["actor_role"]),
            action=action,
            pre_state=pre,
            post_state=post,
            policy_decision=decision,
            reason_code=reason,
        )
        if decision == "deny" and action == "release_sample":
            break

    if not released and run_status == "completed":
        run_status = "failed"
        if final_reason == "ok":
            final_reason = "policy_denied"

    trace_doc = builder.to_trace_document()
    timestamps = [e["timestamp"] for e in trace_doc["events"]]
    return {
        "run_id": rid,
        "scenario_id": workflow.get("scenario_id"),
        "sample_id": sample_id,
        "status": run_status,
        "released": released,
        "final_reason_code": final_reason,
        "started_at": timestamps[0] if timestamps else None,
        "ended_at": timestamps[-1] if timestamps else None,
        "trace": trace_doc,
    }


def write_run_directory(run_dir: Path, run_result: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    trace_path = run_dir / "trace.json"
    trace_path.write_text(
        json.dumps(run_result["trace"], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    meta = {
        "run_id": run_result["run_id"],
        "scenario_id": run_result.get("scenario_id"),
        "sample_id": run_result["sample_id"],
        "status": run_result["status"],
        "released": run_result["released"],
        "final_reason_code": run_result["final_reason_code"],
        "started_at": run_result["started_at"],
        "ended_at": run_result["ended_at"],
        "trace_path": "trace.json",
        "trace_hash": run_result["trace"]["trace_hash"],
    }
    (run_dir / "run_meta.json").write_text(
        json.dumps(meta, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
