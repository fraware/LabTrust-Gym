"""
Tool sandbox: deny-by-default data egress, byte/record caps, data classification.

ToolSandbox(policy_root, tool_id, role_id, ...) enforces:
- Allowlisted egress endpoints (output must not request non-allowlisted destinations).
- max_bytes_out, max_records_out from policy.
- Classification rules: payload fields classified as PII/PHI/IP/Operational; only allowed classes permitted.

Wrap adapters through sandbox or call check_output after execution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

# Reason codes (must match policy/reason_codes/reason_code_registry.v0.1.yaml)
TOOL_EGRESS_DENIED = "TOOL_EGRESS_DENIED"
TOOL_EGRESS_LIMIT_EXCEEDED = "TOOL_EGRESS_LIMIT_EXCEEDED"
TOOL_DATA_CLASS_VIOLATION = "TOOL_DATA_CLASS_VIOLATION"

# Egress keys that indicate destination (deny-by-default: value must be in allowlist).
DEFAULT_EGRESS_INDICATOR_KEYS = ("egress_to", "forward_to", "destination")


def load_tool_boundary_policy(policy_root: Optional[Path] = None) -> Dict[str, Any]:
    """Load tool_boundary_policy from policy_root. Returns root dict or empty dict."""
    if policy_root is None:
        return {}
    path = Path(policy_root) / "policy" / "tool_boundary_policy.v0.1.yaml"
    if not path.exists():
        return {}
    try:
        from labtrust_gym.policy.loader import load_yaml

        data = load_yaml(path)
    except Exception:
        return {}
    root = data.get("tool_boundary_policy") if isinstance(data, dict) else data
    return root if isinstance(root, dict) else {}


def _get_tool_limits(
    boundary_policy: Dict[str, Any],
    tool_id: str,
) -> Tuple[int, int, List[str], Set[str], List[str]]:
    """Return (max_bytes_out, max_records_out, allowed_egress_endpoints, allowed_classes, egress_indicator_keys)."""
    default = boundary_policy.get("default") or {}
    tools = boundary_policy.get("tools") or []
    entry = None
    for t in tools:
        if isinstance(t, dict) and t.get("tool_id") == tool_id:
            entry = t
            break
    if entry is None:
        entry = default
    max_bytes = int(entry.get("max_bytes_out") or default.get("max_bytes_out") or 4096)
    max_records = int(
        entry.get("max_records_out") or default.get("max_records_out") or 100
    )
    allowed_endpoints = list(
        entry.get("allowed_egress_endpoints")
        or default.get("allowed_egress_endpoints")
        or ["internal"]
    )
    out_class = (
        entry.get("output_classification") or default.get("output_classification") or {}
    )
    allowed_classes = set(out_class.get("allowed_classes") or ["Operational"])
    indicator_keys = list(
        boundary_policy.get("egress_indicator_keys") or DEFAULT_EGRESS_INDICATOR_KEYS
    )
    return max_bytes, max_records, allowed_endpoints, allowed_classes, indicator_keys


def _count_records(obj: Any) -> int:
    """Heuristic record count: length of first list value, or 1 for single object."""
    if isinstance(obj, list):
        return len(obj)
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, list):
                return len(v)
        return 1
    return 1


def _collect_values_at_path(obj: Any, path: str) -> List[Any]:
    """Collect values matching path. path may be 'key' or '*.key' (any key named key)."""
    out: List[Any] = []
    if not path or path == ".":
        return [obj]
    parts = path.split(".", 1)
    key, rest = parts[0], (parts[1] if len(parts) > 1 else "")
    if key == "*":
        if isinstance(obj, dict):
            for k, v in obj.items():
                if rest:
                    out.extend(_collect_values_at_path(v, rest))
                else:
                    out.append(v)
        elif isinstance(obj, list):
            for v in obj:
                out.extend(_collect_values_at_path(v, path))
    else:
        if isinstance(obj, dict) and key in obj:
            v = obj[key]
            if rest:
                out.extend(_collect_values_at_path(v, rest))
            else:
                out.append(v)
    return out


def _path_matches_rule(current_path: str, rule_path: str) -> bool:
    """True if current_path matches rule_path (exact or *.key suffix)."""
    if not rule_path:
        return False
    if rule_path == current_path:
        return True
    if rule_path.startswith("*."):
        suffix = rule_path[1:]  # .key
        return current_path.endswith(suffix) or current_path == suffix.lstrip(".")
    return current_path.endswith("." + rule_path)


def _classify_path(path: str, rules: List[Dict[str, Any]]) -> Optional[str]:
    """Return data class for path if any rule matches, else None."""
    for r in rules:
        rule_path = (r.get("path") or "").strip()
        if not rule_path:
            continue
        if _path_matches_rule(path, rule_path):
            return r.get("class") or "Operational"
    return None


def _walk_and_classify(
    obj: Any,
    prefix: str,
    rules: List[Dict[str, Any]],
    allowed_classes: Set[str],
) -> Optional[Tuple[str, str]]:
    """Walk obj; if any key path is classified and not in allowed_classes, return (path, class)."""
    if not rules:
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else k
            cls = _classify_path(p, rules)
            if cls is not None and cls not in allowed_classes:
                return (p, cls)
            rec = _walk_and_classify(v, p, rules, allowed_classes)
            if rec:
                return rec
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{prefix}[{i}]"
            rec = _walk_and_classify(v, p, rules, allowed_classes)
            if rec:
                return rec
    return None


class ToolSandbox:
    """
    Enforces tool boundary policy: allowlisted egress, max bytes/records, data classification.
    """

    __slots__ = (
        "_policy_root",
        "_tool_id",
        "_role_id",
        "_boundary_policy",
    )

    def __init__(
        self,
        policy_root: Optional[Path] = None,
        tool_id: Optional[str] = None,
        role_id: Optional[str] = None,
        boundary_policy: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._policy_root = Path(policy_root) if policy_root else None
        self._tool_id = (tool_id or "").strip() or None
        self._role_id = (role_id or "").strip() or None
        self._boundary_policy = boundary_policy
        if self._boundary_policy is None and self._policy_root:
            self._boundary_policy = load_tool_boundary_policy(self._policy_root)

    def check_output(
        self,
        result: Dict[str, Any],
        tool_id_override: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Enforce boundary on tool output. Returns (allowed, reason_code, details).
        If allowed is True, reason_code and details are None.
        """
        if not self._boundary_policy:
            return True, None, None
        tool_id = (tool_id_override or self._tool_id) or ""
        max_bytes, max_records, allowed_endpoints, allowed_classes, egress_keys = (
            _get_tool_limits(self._boundary_policy, tool_id)
        )
        allowed_set = set(allowed_endpoints)

        # Byte cap
        try:
            raw = json.dumps(result, sort_keys=True, separators=(",", ":"))
            size_bytes = len(raw.encode("utf-8"))
        except (TypeError, ValueError):
            size_bytes = 0
        if size_bytes > max_bytes:
            return (
                False,
                TOOL_EGRESS_LIMIT_EXCEEDED,
                {
                    "limit": "max_bytes_out",
                    "max_bytes_out": max_bytes,
                    "actual_bytes": size_bytes,
                    "tool_id": tool_id,
                },
            )

        # Record cap
        records = _count_records(result)
        if records > max_records:
            return (
                False,
                TOOL_EGRESS_LIMIT_EXCEEDED,
                {
                    "limit": "max_records_out",
                    "max_records_out": max_records,
                    "actual_records": records,
                    "tool_id": tool_id,
                },
            )

        # Egress allowlist: if output contains egress indicator key with value not in allowlist -> deny
        for key in egress_keys:
            if key in result:
                val = result.get(key)
                if val is not None:
                    dest = str(val).strip().lower()
                    if dest and dest not in {e.strip().lower() for e in allowed_set}:
                        return (
                            False,
                            TOOL_EGRESS_DENIED,
                            {
                                "egress_key": key,
                                "destination": str(val),
                                "allowed_egress_endpoints": allowed_endpoints,
                                "tool_id": tool_id,
                            },
                        )

        # Classification: any field classified as PII/PHI/IP must be in allowed_classes
        rules = self._boundary_policy.get("classification_rules") or []
        violation = _walk_and_classify(result, "", rules, allowed_classes)
        if violation:
            path, data_class = violation
            return (
                False,
                TOOL_DATA_CLASS_VIOLATION,
                {
                    "path": path,
                    "data_class": data_class,
                    "allowed_classes": list(allowed_classes),
                    "tool_id": tool_id,
                },
            )

        return True, None, None

    def wrap_adapter(
        self,
        adapter: Callable[[str, Dict[str, Any]], Any],
        tool_id_for_check: Optional[str] = None,
    ) -> Callable[[str, Dict[str, Any]], Any]:
        """Return an adapter that runs the inner adapter then enforces check_output. On violation, raises SandboxViolation."""

        class SandboxViolation(Exception):
            def __init__(
                self,
                reason_code: str,
                message: str,
                details: Optional[Dict[str, Any]] = None,
            ) -> None:
                self.reason_code = reason_code
                self.message = message
                self.details = details or {}
                super().__init__(message)

        def wrapped(tid: str, args: Dict[str, Any]) -> Any:
            out = adapter(tid, args)
            if not isinstance(out, dict):
                return out
            tid_check = tool_id_for_check or tid
            allowed, reason_code, details = self.check_output(
                out, tool_id_override=tid_check
            )
            if not allowed and reason_code:
                raise SandboxViolation(
                    reason_code,
                    details.get("message", reason_code) if details else reason_code,
                    details,
                )
            return out

        return wrapped


def check_output_with_policy(
    result: Dict[str, Any],
    tool_id: str,
    policy_root: Optional[Path] = None,
    boundary_policy: Optional[Dict[str, Any]] = None,
    role_id: Optional[str] = None,
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    One-shot boundary check. Loads policy if boundary_policy not provided.
    Returns (allowed, reason_code, details).
    """
    policy = boundary_policy
    if policy is None and policy_root:
        policy = load_tool_boundary_policy(Path(policy_root))
    if not policy:
        return True, None, None
    sandbox = ToolSandbox(
        policy_root=policy_root,
        tool_id=tool_id,
        role_id=role_id or "",
        boundary_policy=policy,
    )
    return sandbox.check_output(result, tool_id_override=tool_id)
