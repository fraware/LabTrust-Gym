"""Causal event graph fields with hash-chain preservation (LT-VA-07)."""

from __future__ import annotations

from typing import Any, Iterable, Mapping

from labtrust_gym.engine.audit_log import AuditLog, canonical_serialize, hash_event

CLAIM_BOUNDARY = "simulation_research_only_no_clinical_validation"
CAUSAL_MODEL_NOTE = (
    "Declared experimental causal model for research attribution; "
    "not legal responsibility assignment."
)

CAUSAL_OPTIONAL_FIELDS = (
    "parent_event_ids",
    "responsible_principal",
    "authorizing_grant_or_policy",
    "triggering_observation",
    "objects_read",
    "objects_changed",
    "downstream_event_ids",
    "affected_verifier_checks",
    "affected_reward_components",
)


class CausalGraphError(ValueError):
    """Fail-closed causal graph validation error."""


def attach_causal_fields(event: dict[str, Any], causal: Mapping[str, Any] | None) -> dict[str, Any]:
    """Return event copy with optional causal fields; unknown keys fail closed."""
    out = dict(event)
    if not causal:
        out["_causal_model_note"] = CAUSAL_MODEL_NOTE
        return out
    for key in causal:
        if key not in CAUSAL_OPTIONAL_FIELDS:
            raise CausalGraphError(f"unknown causal field: {key}")
    for key in CAUSAL_OPTIONAL_FIELDS:
        if key in causal:
            out[key] = causal[key]
    out["_causal_model_note"] = CAUSAL_MODEL_NOTE
    out["claim_boundary"] = CLAIM_BOUNDARY
    return out


def validate_causal_graph(events: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Validate parent/downstream references and detect cycles."""
    evs = [dict(e) for e in events]
    ids = {str(e.get("event_id")) for e in evs if e.get("event_id")}
    adjacency: dict[str, list[str]] = {i: [] for i in ids}
    for e in evs:
        eid = str(e.get("event_id"))
        for parent in e.get("parent_event_ids") or []:
            parent = str(parent)
            if parent not in ids:
                raise CausalGraphError(f"unknown parent_event_id: {parent}")
            adjacency[parent].append(eid)
        for child in e.get("downstream_event_ids") or []:
            child = str(child)
            if child not in ids:
                raise CausalGraphError(f"unknown downstream_event_id: {child}")
            adjacency[eid].append(child)
    # Cycle detection (DFS)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {i: WHITE for i in ids}

    def dfs(u: str) -> None:
        color[u] = GRAY
        for v in adjacency.get(u, []):
            if color[v] == GRAY:
                raise CausalGraphError(f"causal cycle involving {u} -> {v}")
            if color[v] == WHITE:
                dfs(v)
        color[u] = BLACK

    for node in ids:
        if color[node] == WHITE:
            dfs(node)
    return {
        "valid": True,
        "event_count": len(evs),
        "edge_count": sum(len(v) for v in adjacency.values()),
        "causal_model_note": CAUSAL_MODEL_NOTE,
        "claim_boundary": CLAIM_BOUNDARY,
    }


def append_with_causal(
    audit: AuditLog,
    event: dict[str, Any],
    causal: Mapping[str, Any] | None = None,
) -> tuple[dict[str, Any], bool, dict[str, Any]]:
    """
    Append event (with optional causal fields) to audit log.
    Hash-chain still covers full event bytes including causal fields.
    """
    enriched = attach_causal_fields(event, causal)
    hashchain, broken = audit.append(enriched)
    return hashchain, broken, enriched


def verify_hashchain_events(events: list[Mapping[str, Any]], event_hashes: list[str]) -> bool:
    """Recompute hash chain over event bodies; returns True if matches."""
    prev = ""
    for i, event in enumerate(events):
        body = {k: v for k, v in event.items()}
        event_bytes = canonical_serialize(dict(body))
        h = hash_event(prev, event_bytes)
        if i >= len(event_hashes) or h != event_hashes[i]:
            return False
        prev = h
    return True
