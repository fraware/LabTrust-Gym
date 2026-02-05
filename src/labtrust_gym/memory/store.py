"""
Memory store: authenticated writes, schema-limited content, TTL/decay, poison filtering.

put(entry, writer_agent_id, signature, ttl) enforces: signature (when required), schema, no poison.
get(query, role_id) returns only non-expired entries and filters poison/instruction-override.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from labtrust_gym.memory.validators import (
    MEM_POISON_DETECTED,
    MEM_WRITE_SCHEMA_FAIL,
    check_poison_and_instruction_override,
    filter_poison_from_entries,
    load_memory_policy,
    validate_entry_schema,
)

MEM_WRITE_UNAUTHENTICATED = "MEM_WRITE_UNAUTHENTICATED"
MEM_RETRIEVAL_FILTERED = "MEM_RETRIEVAL_FILTERED"


def _canonical_bytes(obj: Dict[str, Any]) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _verify_memory_signature(
    entry: Dict[str, Any],
    writer_agent_id: str,
    signature: Optional[str],
    ttl: int,
    key_store: Any,
) -> Tuple[bool, Optional[str]]:
    """
    Verify signature for (entry, writer_agent_id, ttl) using key_store.
    key_store: agent_id -> (private_key, public_key_b64) as in coordination.identity.
    Returns (ok, reason_code).
    """
    if not signature or not key_store:
        return False, MEM_WRITE_UNAUTHENTICATED
    try:
        from labtrust_gym.coordination.identity import verify_message

        payload = {**entry, "ttl": ttl}
        payload_hash = _canonical_bytes(payload).hex()[:32]
        envelope = {
            "sender_id": writer_agent_id,
            "message_type": "MEM_PUT",
            "payload": payload,
            "payload_hash": payload_hash,
            "nonce": 0,
            "epoch": 0,
            "signature": signature,
        }
        ok, _, reason = verify_message(envelope, key_store)
        if ok:
            return True, None
        return False, MEM_WRITE_UNAUTHENTICATED
    except Exception:
        return False, MEM_WRITE_UNAUTHENTICATED


class MemoryStore:
    """
    In-memory store with authenticated writes, TTL expiry, and poison filtering on get.
    """

    __slots__ = (
        "_policy",
        "_policy_root",
        "_key_store",
        "_entries",
        "_now_ts_fn",
    )

    def __init__(
        self,
        policy_root: Optional[Path] = None,
        policy: Optional[Dict[str, Any]] = None,
        key_store: Optional[Dict[str, Any]] = None,
        now_ts_fn: Optional[Callable[[], int]] = None,
    ) -> None:
        self._policy_root = Path(policy_root) if policy_root else None
        self._policy = (
            policy
            if policy is not None
            else load_memory_policy(self._policy_root)
        )
        self._key_store = key_store or {}
        self._now_ts_fn = now_ts_fn or (lambda: 0)
        self._entries: List[Dict[str, Any]] = []

    def put(
        self,
        entry: Dict[str, Any],
        writer_agent_id: str,
        signature: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
        """
        Store an entry. Returns (ok, reason_code, details).
        Enforces: authenticated write (when policy requires), schema, no poison; TTL bounds.
        """
        policy = self._policy
        ttl_bounds = policy.get("ttl_bounds") or {}
        min_ttl = int(ttl_bounds.get("min_ttl_s") or 0)
        max_ttl = int(ttl_bounds.get("max_ttl_s") or 86400)
        default_ttl = int(policy.get("default_ttl_s") or 3600)
        ttl_s = int(ttl) if ttl is not None else default_ttl
        if ttl_s < min_ttl or ttl_s > max_ttl:
            return False, MEM_WRITE_SCHEMA_FAIL, {"reason": "ttl_out_of_bounds", "ttl": ttl_s}

        if policy.get("require_authenticated_writes"):
            ok, code = _verify_memory_signature(
                entry, writer_agent_id, signature, ttl_s,
                self._key_store,
            )
            if not ok:
                return False, code, None

        ok, code = validate_entry_schema(entry, policy)
        if not ok:
            return False, code, None

        content = entry.get("content") or entry.get("summary") or ""
        text = str(content)
        ok, code, mid = check_poison_and_instruction_override(text, policy)
        if not ok:
            return False, code, {"matched_id": mid}

        now = self._now_ts_fn()
        stored = {
            **entry,
            "_writer": writer_agent_id,
            "_expires_at": now + ttl_s,
            "_ttl": ttl_s,
        }
        self._entries.append(stored)
        return True, None, None

    def get(
        self,
        query: Optional[Dict[str, Any]] = None,
        role_id: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], int, Optional[str]]:
        """
        Retrieve entries: drop expired, filter poison. Returns (entries, filtered_count, emit_if_filtered).
        query: optional filter (e.g. by role/tags); currently unused, all non-expired considered.
        role_id: optional; reserved for future RBAC-scoped retrieval.
        """
        now = self._now_ts_fn()
        non_expired = [e for e in self._entries if (e.get("_expires_at") or 0) > now]
        filtered, removed = filter_poison_from_entries(
            non_expired, self._policy, content_key="content"
        )
        out: List[Dict[str, Any]] = []
        for e in filtered:
            clean = {k: v for k, v in e.items() if not k.startswith("_")}
            out.append(clean)
        emit = MEM_RETRIEVAL_FILTERED if removed > 0 else None
        return out, removed, emit

    def reset(self) -> None:
        """Clear all entries (e.g. new episode)."""
        self._entries.clear()


def load_memory_policy_from_root(policy_root: Optional[Path] = None) -> Dict[str, Any]:
    """Convenience: load memory policy from repo root."""
    return load_memory_policy(Path(policy_root) if policy_root else None)
