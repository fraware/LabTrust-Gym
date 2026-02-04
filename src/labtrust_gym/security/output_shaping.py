"""
B009: Central output shaping and redaction for online endpoints and public artifacts.

- Summary views by default: aggregated metrics, blocked counts, violation counts.
- Full logs/receipts only for admin (enforced at endpoint level).
- Obfuscation: hash/truncate specimen and work IDs; strip raw signatures (keep validity/key_id);
  reduce LLM fidelity (hashes + minimal metadata, no full prompts).
- Shared pipeline for B003 (public release) and B009 (online endpoints).
"""

from __future__ import annotations

import hashlib
from typing import Any, Dict, List, Optional, Set, Tuple

# Keys that must never appear in viewer-facing or public summary output.
# Used to validate that summary builders do not leak sensitive data.
FORBIDDEN_IN_SUMMARY: Set[str] = frozenset(
    {
        "signature",  # raw signature bytes
        "raw_prompt",
        "prompt",
        "raw_response",
        "response",
        "api_key",
        "secret",
        "password",
        "token",
        "private_key",
        "episode_log",
        "entries",  # raw log entries are admin-only; summary uses aggregates only
    }
)

# Top-level keys allowed in run summary (viewer-safe). Additional nested keys
# for metrics are constrained to numeric/aggregate names.
ALLOWED_SUMMARY_TOP_LEVEL: Set[str] = frozenset(
    {
        "n_episodes",
        "task",
        "agent_baseline_id",
        "partner_id",
        "throughput_mean",
        "throughput_std",
        "violations_total",
        "blocked_count",
        "blocked_by_reason_code",
        "violations_by_invariant_id",
        "on_time_rate_mean",
        "p50_turnaround_s_mean",
        "p95_turnaround_s_mean",
        "critical_communication_compliance_rate_mean",
        "steps_total",
    }
)


def _violations_total_from_metrics(metrics: Dict[str, Any]) -> int:
    """Sum violation counts from violations_by_invariant_id."""
    vbi = metrics.get("violations_by_invariant_id") or {}
    if isinstance(vbi, dict):
        return sum(int(x) for x in vbi.values())
    return 0


def _blocked_count_from_metrics(metrics: Dict[str, Any]) -> int:
    """Sum blocked counts from blocked_by_reason_code."""
    bbr = metrics.get("blocked_by_reason_code") or {}
    if isinstance(bbr, dict):
        return sum(int(x) for x in bbr.values())
    return 0


def build_run_summary(
    results_or_episodes: Dict[str, Any] | List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build a viewer-safe run summary: aggregated metrics, blocked count, violation count.

    Input: either a results dict (with "episodes" list) or a list of episode dicts
    (each with "metrics"). Output contains only aggregate fields; no raw log entries,
    prompts, or signatures.
    """
    if isinstance(results_or_episodes, list):
        episodes = results_or_episodes
        task = None
        agent_baseline_id = None
        partner_id = None
    else:
        data = results_or_episodes
        episodes = data.get("episodes") or []
        task = data.get("task")
        agent_baseline_id = data.get("agent_baseline_id")
        partner_id = data.get("partner_id")

    n_episodes = len(episodes)
    throughput_sum = 0
    violations_total = 0
    blocked_count = 0
    blocked_by_reason: Dict[str, int] = {}
    violations_by_invariant: Dict[str, int] = {}
    on_time_rates: List[float] = []
    p50_tat: List[float] = []
    p95_tat: List[float] = []
    critical_compliance: List[float] = []
    steps_total = 0

    for ep in episodes:
        if not isinstance(ep, dict):
            continue
        metrics = ep.get("metrics") or {}
        throughput_sum += int(metrics.get("throughput") or 0)
        violations_total += _violations_total_from_metrics(metrics)
        blocked_count += _blocked_count_from_metrics(metrics)
        for k, v in (metrics.get("blocked_by_reason_code") or {}).items():
            blocked_by_reason[str(k)] = blocked_by_reason.get(str(k), 0) + int(v)
        for k, v in (metrics.get("violations_by_invariant_id") or {}).items():
            violations_by_invariant[str(k)] = violations_by_invariant.get(
                str(k), 0
            ) + int(v)
        r = metrics.get("on_time_rate")
        if r is not None:
            on_time_rates.append(float(r))
        r = metrics.get("p50_turnaround_s")
        if r is not None:
            p50_tat.append(float(r))
        r = metrics.get("p95_turnaround_s")
        if r is not None:
            p95_tat.append(float(r))
        r = metrics.get("critical_communication_compliance_rate")
        if r is not None:
            critical_compliance.append(float(r))
        steps_total += int(metrics.get("steps") or 0)

    def _mean(vals: List[float]) -> Optional[float]:
        if not vals:
            return None
        return sum(vals) / len(vals)

    summary: Dict[str, Any] = {
        "n_episodes": n_episodes,
        "throughput_mean": (throughput_sum / n_episodes) if n_episodes else 0,
        "violations_total": violations_total,
        "blocked_count": blocked_count,
        "blocked_by_reason_code": blocked_by_reason,
        "violations_by_invariant_id": violations_by_invariant,
        "steps_total": steps_total,
    }
    if task is not None:
        summary["task"] = task
    if agent_baseline_id is not None:
        summary["agent_baseline_id"] = agent_baseline_id
    if partner_id is not None:
        summary["partner_id"] = partner_id
    ot = _mean(on_time_rates)
    if ot is not None:
        summary["on_time_rate_mean"] = ot
    p50 = _mean(p50_tat)
    if p50 is not None:
        summary["p50_turnaround_s_mean"] = p50
    p95 = _mean(p95_tat)
    if p95 is not None:
        summary["p95_turnaround_s_mean"] = p95
    cc = _mean(critical_compliance)
    if cc is not None:
        summary["critical_communication_compliance_rate_mean"] = cc
    return summary


def summary_contains_no_forbidden_fields(
    summary: Dict[str, Any],
) -> Tuple[bool, List[str]]:
    """
    Check that a summary dict contains no forbidden keys (at any nesting).
    Returns (True, []) if safe; (False, [list of forbidden keys found]) otherwise.
    """
    found: List[str] = []
    forbidden_lower = {k.lower() for k in FORBIDDEN_IN_SUMMARY}

    def scan(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in forbidden_lower:
                    found.append(f"{path}.{k}" if path else k)
                scan(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                scan(item, f"{path}[{i}]")

    scan(summary)
    return (len(found) == 0, found)


def obfuscate_identifier(
    value: str,
    mode: str = "hash",
    truncate_len: int = 4,
) -> str:
    """
    Obfuscate a specimen_id or work_id for public/summary output.

    mode: "hash" -> sha256 hex prefix (e.g. 16 chars); "truncate" -> first truncate_len chars + "..."
    """
    if not value or not isinstance(value, str):
        return ""
    if mode == "hash":
        h = hashlib.sha256(value.encode("utf-8")).hexdigest()
        return h[:16]
    if mode == "truncate":
        if len(value) <= truncate_len:
            return value[:truncate_len]
        return value[:truncate_len] + "..."
    return value


def shape_signature_verification(
    sv: Dict[str, Any],
    keep_raw: bool = False,
) -> Dict[str, Any]:
    """
    Return a signature_verification view: by default only validity + key_id (no raw signature).
    """
    if not sv or not isinstance(sv, dict):
        return {}
    if keep_raw:
        return dict(sv)
    return {
        "passed": sv.get("passed"),
        "reason_code": sv.get("reason_code"),
        "key_id": sv.get("key_id"),
    }


def shape_llm_decision(
    llm: Dict[str, Any],
    full_fidelity: bool = False,
) -> Dict[str, Any]:
    """
    Return LLM decision view: by default hashes + minimal metadata only (no full prompt/response).
    """
    if not llm or not isinstance(llm, dict):
        return {}
    if full_fidelity:
        return dict(llm)
    out: Dict[str, Any] = {}
    for key in (
        "prompt_sha256",
        "response_sha256",
        "backend_id",
        "model_id",
        "latency_ms",
        "error_code",
        "repair_attempted",
        "repair_succeeded",
    ):
        if key in llm:
            out[key] = llm[key]
    return out


def shape_episode_log_entry_for_role(
    entry: Dict[str, Any],
    role: str,
    obfuscate_specimen: bool = True,
    obfuscate_work_id: bool = True,
    id_mode: str = "hash",
) -> Dict[str, Any]:
    """
    Shape a single episode log entry for output. Viewer should not receive raw entries
    (use build_run_summary instead). For admin, optionally obfuscate identifiers and
    strip raw signature / full LLM content.
    """
    from labtrust_gym.online.authz import ROLE_ADMIN

    out = dict(entry)
    if role != ROLE_ADMIN:
        # Caller should not use this for viewer; return minimal
        return {
            "t_s": out.get("t_s"),
            "action_type": out.get("action_type"),
            "status": out.get("status"),
        }

    if obfuscate_specimen or obfuscate_work_id:
        args = out.get("args")
        if isinstance(args, dict):
            args = dict(args)
            if obfuscate_specimen and "specimen_id" in args:
                args["specimen_id"] = obfuscate_identifier(
                    str(args["specimen_id"]), mode=id_mode
                )
            if obfuscate_work_id and "work_id" in args:
                args["work_id"] = obfuscate_identifier(
                    str(args["work_id"]), mode=id_mode
                )
            out["args"] = args

    sv = out.get("signature_verification")
    if sv:
        out["signature_verification"] = shape_signature_verification(sv, keep_raw=False)

    llm = out.get("llm_decision")
    if llm:
        out["llm_decision"] = shape_llm_decision(llm, full_fidelity=False)

    return out


def shape_for_role(
    data: Dict[str, Any],
    role: str | None,
    *,
    want_summary: bool = True,
    want_raw_logs: bool = False,
) -> Dict[str, Any]:
    """
    Shape payload for role. Viewer: summary only. Admin: may include raw logs if want_raw_logs.
    """
    from labtrust_gym.online.authz import ROLE_ADMIN, has_privilege

    if role is None or not has_privilege(role, ROLE_ADMIN):
        # Viewer or runner: return summary view only
        episodes = data.get("episodes") or []
        return build_run_summary(
            {
                "episodes": episodes,
                **{
                    k: data.get(k)
                    for k in ("task", "agent_baseline_id", "partner_id")
                    if k in data
                },
            }
        )

    # Admin
    out: Dict[str, Any] = {}
    if want_summary:
        out["summary"] = build_run_summary(data)
    if want_raw_logs and data.get("episode_log_entries"):
        out["episode_log_entries"] = data["episode_log_entries"]
    elif want_raw_logs:
        out["episode_log_entries"] = []
    return out if out else build_run_summary(data)
