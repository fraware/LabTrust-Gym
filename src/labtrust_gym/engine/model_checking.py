"""
Bounded trace checker for critical-path safety.

Evaluates invariants (safety rules from the policy registry) over recorded
event traces. Input traces match the episode log or golden runner format.
No external model checker is used. Outputs a safety result, the trace, and
violations with evidence; writes model_check_report.json and
model_check_report.md into the given output directory.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from labtrust_gym.policy.invariants_registry import (
    InvariantEntry,
    load_invariant_registry,
)

# -----------------------------
# Data contract: trace format
# -----------------------------
# Event trace: list of step entries. Each entry must have:
#   - "event": dict with at least event_id, t_s, agent_id, action_type, args (optional)
#   - "result": dict with at least status, violations (list of {invariant_id, status, reason_code?, message?})
# This matches episode log / golden runner step output.
TraceEntry = dict[str, Any]
EventTrace = list[TraceEntry]


@dataclass
class Violation:
    """A single invariant violation on the trace."""

    invariant_id: str
    step_index: int
    evidence: dict[str, Any]
    message: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _load_registry_titles(policy_root: Path | None) -> dict[str, str]:
    """Build invariant_id -> title from registry. Uses default policy path if None."""
    root = policy_root or Path("policy")
    path = root / "invariants" / "invariant_registry.v1.0.yaml"
    entries: list[InvariantEntry] = load_invariant_registry(path)
    out: dict[str, str] = {}
    for e in entries:
        if e.invariant_id:
            out[e.invariant_id] = e.title or e.invariant_id
    for name in ("invariant_registry.v1.0.zones.yaml",):
        p = root / "invariants" / name
        if p.exists():
            more = load_invariant_registry(p)
            for e in more:
                if e.invariant_id and e.invariant_id not in out:
                    out[e.invariant_id] = e.title or e.invariant_id
    return out


def _evidence_from_entry(entry: TraceEntry) -> dict[str, Any]:
    """Extract evidence pointers from a trace entry."""
    event = entry.get("event") or {}
    result = entry.get("result") or {}
    return {
        "event_id": event.get("event_id"),
        "t_s": event.get("t_s"),
        "agent_id": event.get("agent_id"),
        "action_type": event.get("action_type"),
        "status": result.get("status"),
    }


def check_critical_path_safety(
    event_trace: EventTrace,
    invariant_ids: list[str],
    max_steps: int = 100,
    output_dir: Path | None = None,
    policy_root: Path | None = None,
) -> tuple[bool, list[TraceEntry], list[Violation]]:
    """
    Bounded trace invariant checker: verify no step in the trace violates
    the given invariants within max_steps.

    Consumes an event trace (list of {event, result} as produced by episode
    log or golden runner). Loads invariant definitions from the policy pack;
    evaluates violations and returns (safe, trace, violations). When
    output_dir is set, writes model_check_report.json and model_check_report.md.

    Args:
        event_trace: List of step entries; each has "event" and "result" with
            result.violations containing {invariant_id, status, reason_code?, message?}.
        invariant_ids: Invariant IDs that must not be violated (e.g. critical).
        max_steps: Maximum steps to consider; trace is truncated.
        output_dir: If set, write model_check_report.json and .md here.
        policy_root: Policy root for loading invariant registry; default cwd.

    Returns:
        (safe, trace, violations). safe is False if any violation found;
        trace is the truncated trace; violations list has step_index, evidence, message.
    """
    ids_set = frozenset(invariant_ids or [])
    titles = _load_registry_titles(policy_root)
    bounded: list[TraceEntry] = list(event_trace[: max_steps + 1]) if event_trace else []
    violations: list[Violation] = []

    for step_index, entry in enumerate(bounded):
        result = entry.get("result")
        if not isinstance(result, dict):
            continue
        for v in result.get("violations") or []:
            inv_id = v.get("invariant_id")
            if not inv_id or inv_id not in ids_set:
                continue
            if (v.get("status") or "").upper() != "VIOLATION":
                continue
            title = titles.get(inv_id) or inv_id
            reason = v.get("reason_code") or v.get("message") or "violation"
            message = f"{inv_id}: {title} — {reason}"
            evidence = _evidence_from_entry(entry)
            if v.get("details"):
                evidence["details"] = v.get("details")
            violations.append(
                Violation(
                    invariant_id=inv_id,
                    step_index=step_index,
                    evidence=evidence,
                    message=message,
                )
            )

    safe = len(violations) == 0

    if output_dir is not None:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        report = {
            "safe": safe,
            "max_steps": max_steps,
            "steps_checked": len(bounded),
            "violations": [asdict(v) for v in violations],
            "invariant_ids_checked": list(ids_set),
        }
        json_path = output_dir / "model_check_report.json"
        json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        md_lines = [
            "# Model check report",
            "",
            f"- **Safe:** {safe}",
            f"- **Steps checked:** {len(bounded)}",
            f"- **Violations:** {len(violations)}",
            "",
        ]
        if violations:
            md_lines.append("## Violations")
            md_lines.append("")
            for v in violations:
                md_lines.append(f"- **{v.invariant_id}** (step {v.step_index}): {v.message}")
                md_lines.append(f"  - Evidence: {json.dumps(v.evidence)}")
                md_lines.append("")
        md_path = output_dir / "model_check_report.md"
        md_path.write_text("\n".join(md_lines), encoding="utf-8")

    return (safe, bounded, violations)
