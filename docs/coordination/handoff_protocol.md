# Handoff protocol: planner, repair, detector

This document specifies the message envelope and invocation order for the planner-to-repair-to-detector handoff. The implementation follows this spec; no separate wire format exists beyond the in-process function calls described below.

## Invocation order

1. **Planner path:** Each env step, the runner (or the coordination method) invokes the planner/proposal backend to produce a joint proposal (e.g. allocation, bids, or central plan). One call per step unless the method uses a multi-step protocol (e.g. round_robin bidder).
2. **Repair path:** When the kernel or shield **blocks** some actions (e.g. RBAC, signature, or invariant violation), the runner invokes the repair backend with the blocked actions and context. Repair returns repaired actions; the runner merges or retries. So: planner output -> (optional) shield/kernel -> on block -> repair backend -> merged result.
3. **Detector path:** After step outcomes are available, the detector is invoked (e.g. each step or on specific events). It receives a compact event summary and comms stats and returns a detect + recommend result (e.g. throttle, freeze_zone, kill_switch, none). The advisor layer applies policy-valid containment.

So the handoff is **planner (every step) -> repair (on block) -> detector (every step or on events)**. All three use the same per-role backends and coordinator guardrails when configured.

## Message envelope: planner to repair

When the runner calls the repair backend, it passes a **repair input** dict. Schema and builder: `src/labtrust_gym/baselines/coordination/repair_input.py` (`build_repair_input`).

| Field | Type | Description |
|-------|------|-------------|
| `scale_config_snapshot` | dict | Sanitized scale config (sorted keys for determinism). No secrets; used for context. |
| `last_accepted_plan_summary` | dict | E.g. `route_hash`, `step_idx`; no wall-clock timestamps. |
| `blocked_actions` | list[dict] | Each item: `agent_id`, `action_type`, `reason_code`. Stable order. |
| `constraint_summary` | dict | Allowed actions and invariants (e.g. INV-ROUTE-001, INV-ROUTE-002). |
| `red_team_flags` | list[str] (optional) | E.g. `["comms_poison"]`; sorted for stability. |

Repair backend returns: `(list[tuple[agent_id, action_type, args]], meta)` where meta can include `backend_id`, `reason_code`, `latency_ms`.

**Versioning:** The repair input does not currently carry an explicit schema version. Forward compatibility can be added later via an optional `version` field (e.g. `"repair_input_version": "0.1"`) in the top-level dict.

## Message envelope: step outcomes to detector

The detector backend is invoked with:

- **step:** int (env step index).
- **event_summary:** dict with at least `obs_snapshot` or `obs`, and optionally `agent_count`, `obs_keys`, `comms_keys`. Compact; keys may be truncated (e.g. `LIVE_DETECTOR_OBS_KEYS_LIMIT`, `LIVE_DETECTOR_COMMS_KEYS_LIMIT` in `detector_advisor.py`).
- **comms_stats:** dict or None; comms/network stats for the step.

Detector returns: `DetectorOutput(detect=DetectResult(...), recommend=RecommendResult(...))`. See `src/labtrust_gym/baselines/coordination/assurance/detector_advisor.py` for the exact dataclasses.

**Versioning:** Detector payload does not currently carry an explicit version. A future `event_summary.version` or `detector_payload_version` can be added for compatibility.

## References

- Repair input builder: `src/labtrust_gym/baselines/coordination/repair_input.py`
- Detector interface: `LiveDetectorBackend.detect(step, event_summary, comms_stats)` in `src/labtrust_gym/baselines/coordination/assurance/detector_advisor.py`
- [Multi-LLM protocols](multi_llm_protocols.md): handoffs and round_robin
