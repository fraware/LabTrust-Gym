"""
Context builder v0.2: bounded, injection-hardened state summary for LLM.

- build_state_summary_v0_2(engine_state, policy, agent_id, role_id, now_ts_s,
  timing_mode) -> dict conforming to state_summary v0.2 contract.
- Caps: cap_k=10 on queue.by_device, work lists, tokens.active, invariants.
- Untrusted free text (specimen/scenario metadata): truncate 200 chars, escape
  newlines, wrap under untrusted_notes.samples with source tag; never in main
  decision fields.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

CAP_K = 10
UNTRUSTED_MAX_CHARS = 200


def _truncate_and_escape(text: str, max_chars: int = UNTRUSTED_MAX_CHARS) -> str:
    """Truncate to max_chars and escape newlines (injection hardening)."""
    if not isinstance(text, str):
        text = str(text)
    s = text.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", "\\n")
    if len(s) > max_chars:
        s = s[:max_chars] + "..."
    return s


def _collect_untrusted_samples(engine_state: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Collect free text from engine_state that must be treated as untrusted.
    Returns list of {"source": "specimen_note"|"scenario_note"|..., "text": "..."}
    with truncated, escaped text. Do not place free text in main decision fields.
    """
    samples: List[Dict[str, str]] = []
    # Map engine_state key -> explicit tag for audit
    source_tag: Dict[str, str] = {
        "specimen_notes": "specimen_note",
        "scenario_notes": "scenario_note",
        "notes": "note",
        "metadata_notes": "metadata_note",
    }
    for key in ("specimen_notes", "scenario_notes", "notes", "metadata_notes"):
        raw = engine_state.get(key)
        if raw is None:
            continue
        tag = source_tag.get(key, key)
        if isinstance(raw, list):
            for i, item in enumerate(raw):
                t = item if isinstance(item, str) else json.dumps(item)
                samples.append(
                    {
                        "source": tag,
                        "text": _truncate_and_escape(t),
                    }
                )
                if len(samples) >= CAP_K:
                    return samples[:CAP_K]
        elif isinstance(raw, str):
            samples.append({"source": tag, "text": _truncate_and_escape(raw)})
        else:
            samples.append({"source": tag, "text": _truncate_and_escape(str(raw))})
        if len(samples) >= CAP_K:
            return samples[:CAP_K]
    return samples[:CAP_K]


def _cap_list(items: List[Any], cap: int = CAP_K) -> List[Any]:
    """Return first cap items."""
    if not isinstance(items, list):
        return []
    return list(items)[:cap]


def build_state_summary_v0_2(
    engine_state: Dict[str, Any],
    policy: Dict[str, Any],
    agent_id: str,
    role_id: str,
    now_ts_s: int,
    timing_mode: str = "explicit",
) -> Dict[str, Any]:
    """
    Build state summary v0.2: bounded, injection-hardened, decision-relevant only.

    engine_state: dict with optional zone_id, site_id, queue_by_device,
    active_runs, pending_results, pending_criticals, active_tokens,
    recent_violations, enforcement_state, log_frozen; optional specimen_notes etc.
    for untrusted_notes.
    policy: dict with strict_signatures, policy_fingerprint, partner_id (and
    optionally allowed_actions, etc.).
    """
    partner_id = str(policy.get("partner_id") or engine_state.get("partner_id") or "")
    policy_fingerprint = str(
        policy.get("policy_fingerprint") or engine_state.get("policy_fingerprint") or ""
    )
    strict_signatures = bool(
        policy.get("strict_signatures")
        or engine_state.get("strict_signatures")
        or False
    )
    log_frozen = bool(
        policy.get("log_frozen")
        if "log_frozen" in policy
        else engine_state.get("log_frozen", False)
    )

    zone_id = engine_state.get("zone_id") or engine_state.get("agent_zone") or ""
    site_id = engine_state.get("site_id") or "SITE_HUB"

    queue_by_device = _cap_list(
        engine_state.get("queue_by_device") or [],
        cap=CAP_K,
    )
    for i, q in enumerate(queue_by_device):
        if not isinstance(q, dict):
            queue_by_device[i] = {"device_id": "", "queue_head": "", "queue_len": 0}
        else:
            queue_by_device[i] = {
                "device_id": str(q.get("device_id", "")),
                "queue_head": str(q.get("queue_head", "")),
                "queue_len": (
                    int(q.get("queue_len", 0)) if q.get("queue_len") is not None else 0
                ),
            }

    active_runs = _cap_list(engine_state.get("active_runs") or [], cap=CAP_K)
    active_runs = [
        (
            {
                "device_id": str(r.get("device_id", "")),
                "work_id": str(r.get("work_id", "")),
                "status": str(r.get("status", "RUNNING")),
            }
            if isinstance(r, dict)
            else {"device_id": "", "work_id": "", "status": "RUNNING"}
        )
        for r in active_runs
    ]

    pending_results = _cap_list(engine_state.get("pending_results") or [], cap=CAP_K)
    pending_results = [
        (
            {
                "result_id": str(r.get("result_id", "")),
                "status": str(r.get("status", "HOLD")),
                "criticality": str(r.get("criticality", "")),
            }
            if isinstance(r, dict)
            else {"result_id": "", "status": "HOLD", "criticality": ""}
        )
        for r in pending_results
    ]

    pending_criticals = _cap_list(
        engine_state.get("pending_criticals") or [], cap=CAP_K
    )
    pending_criticals = [
        (
            {
                "result_id": str(c.get("result_id", "")),
                "tier": int(c.get("tier", 0)) if c.get("tier") is not None else 0,
                "ack_due_in_s": (
                    int(c.get("ack_due_in_s", 0))
                    if c.get("ack_due_in_s") is not None
                    else 0
                ),
            }
            if isinstance(c, dict)
            else {"result_id": "", "tier": 0, "ack_due_in_s": 0}
        )
        for c in pending_criticals
    ]

    active_tokens = _cap_list(engine_state.get("active_tokens") or [], cap=CAP_K)
    active_tokens = [
        (
            {
                "token_id": str(t.get("token_id", "")),
                "token_type": str(t.get("token_type", "")),
                "expires_in_s": (
                    int(t.get("expires_in_s", 0))
                    if t.get("expires_in_s") is not None
                    else 0
                ),
            }
            if isinstance(t, dict)
            else {"token_id": "", "token_type": "", "expires_in_s": 0}
        )
        for t in active_tokens
    ]

    recent_violations = _cap_list(
        engine_state.get("recent_violations") or [], cap=CAP_K
    )
    recent_violations = [
        (
            {
                "invariant_id": str(v.get("invariant_id", "")),
                "severity": str(v.get("severity", "")),
                "at_ts_s": (
                    int(v.get("at_ts_s", 0)) if v.get("at_ts_s") is not None else 0
                ),
            }
            if isinstance(v, dict)
            else {"invariant_id": "", "severity": "", "at_ts_s": 0}
        )
        for v in recent_violations
    ]

    enforcement = engine_state.get("enforcement_state") or {}
    if not isinstance(enforcement, dict):
        enforcement = {}
    throttles = _cap_list(enforcement.get("throttles") or [], cap=CAP_K)
    frozen_zones = _cap_list(enforcement.get("frozen_zones") or [], cap=CAP_K)

    untrusted_samples = _collect_untrusted_samples(engine_state)

    return {
        "schema_version": "0.2",
        "partner_id": partner_id,
        "policy_fingerprint": policy_fingerprint,
        "agent_id": str(agent_id),
        "role_id": str(role_id),
        "now_ts_s": int(now_ts_s),
        "timing_mode": str(timing_mode).strip().lower(),
        "strict_signatures": strict_signatures,
        "log_frozen": log_frozen,
        "location": {"site_id": site_id, "zone_id": zone_id},
        "queue": {
            "by_device": queue_by_device,
            "cap_k": CAP_K,
        },
        "work": {
            "active_runs": active_runs,
            "pending_results": pending_results,
            "pending_criticals": pending_criticals,
            "cap_k": CAP_K,
        },
        "tokens": {"active": active_tokens, "cap_k": CAP_K},
        "invariants": {
            "recent_violations": recent_violations,
            "enforcement_state": {
                "throttles": throttles,
                "frozen_zones": frozen_zones,
            },
        },
        "untrusted_notes": {
            "present": len(untrusted_samples) > 0,
            "samples": untrusted_samples,
        },
    }
