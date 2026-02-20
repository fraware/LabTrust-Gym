"""
Replay-safe coordination message bus.

Messages are verified on receive. Each message carries a sender id, nonce, and
epoch. The bus rejects messages whose epoch does not match the current epoch
(from epoch_fn); use a new epoch per episode so old messages cannot be replayed.
Each (sender_id, nonce) is recorded; a duplicate nonce from the same sender is
rejected (COORD_REPLAY_DETECTED). All messages must be signed and verified via
identity.sign_message/verify_message. Envelope keys (KEY_SENDER_ID, KEY_NONCE,
KEY_EPOCH, KEY_MESSAGE_TYPE, KEY_PAYLOAD) are canonical. Violations are returned
as step-result fragments for the runner to log.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from labtrust_gym.coordination.identity import (
    COORD_REPLAY_DETECTED,
    COORD_SENDER_NOT_AUTHORIZED,
    COORD_SIGNATURE_INVALID,
    KEY_EPOCH,
    KEY_MESSAGE_TYPE,
    KEY_NONCE,
    KEY_PAYLOAD,
    KEY_SENDER_ID,
    verify_message,
)


def _default_epoch_fn() -> int:
    """Default: epoch 0 (e.g. single-episode bus)."""
    return 0


class SignedMessageBus:
    """
    Coordination message bus with verify-on-receive, nonce tracking, and epoch binding.
    Call receive(envelope) to submit a signed message; returns (accepted, delivered, violation_result).
    violation_result is a step-result fragment (violations + emits) for the runner.
    """

    __slots__ = (
        "_key_store",
        "_allowed_message_types",
        "_high_impact_require_countersign",
        "_allowed_senders",
        "_epoch_fn",
        "_seen_nonces",
    )

    def __init__(
        self,
        key_store: dict[str, tuple[Any, str]],
        identity_policy: dict[str, Any] | None = None,
        epoch_fn: Callable[[], int] | None = None,
    ) -> None:
        """
        key_store: agent_id -> (private_key, public_key_b64) for verify (only public used).
        identity_policy: optional dict with allowed_message_types (list),
            high_impact_require_countersign (list of message_type),
            allowed_senders (optional: list of agent_id or null for any in key_store).
        epoch_fn: callable that returns current epoch (default: always 0).
        """
        self._key_store = key_store
        policy = identity_policy or {}
        self._allowed_message_types: set[str] = set(policy.get("allowed_message_types") or [])
        self._high_impact_require_countersign: set[str] = set(policy.get("high_impact_require_countersign") or [])
        allowed = policy.get("allowed_senders")
        self._allowed_senders: set[str] | None = set(allowed) if isinstance(allowed, list) else None
        self._epoch_fn = epoch_fn or _default_epoch_fn
        self._seen_nonces: set[tuple[str, int]] = set()

    def reset(self) -> None:
        """Clear nonce history (e.g. for new episode)."""
        self._seen_nonces.clear()

    def receive(
        self,
        envelope: dict[str, Any],
    ) -> tuple[bool, dict[str, Any] | None, dict[str, Any] | None]:
        """
        Verify and accept or reject a signed coordination message.
        Returns (accepted, delivered_message, violation_step_result).
        - accepted True: delivered_message is the verified envelope (or normalized delivery dict).
        - accepted False: violation_step_result is a step-result fragment with "violations" and "emits".
        """
        # 1) Signature
        ok, sender_id, reason = verify_message(envelope, self._key_store)
        if not ok:
            return (
                False,
                None,
                _violation_step_result(reason or COORD_SIGNATURE_INVALID, envelope),
            )
        assert sender_id is not None

        # 2) Replay (nonce)
        nonce = envelope.get(KEY_NONCE)
        if nonce is None and KEY_NONCE in envelope:
            nonce = envelope[KEY_NONCE]
        try:
            nonce_int = int(nonce) if nonce is not None else None
        except (TypeError, ValueError):
            nonce_int = None
        if nonce_int is None:
            return (
                False,
                None,
                _violation_step_result(COORD_SIGNATURE_INVALID, envelope),
            )
        key_nonce = (sender_id, nonce_int)
        if key_nonce in self._seen_nonces:
            return (
                False,
                None,
                _violation_step_result(COORD_REPLAY_DETECTED, envelope),
            )
        self._seen_nonces.add(key_nonce)

        # 3) Epoch binding
        current_epoch = self._epoch_fn()
        msg_epoch = envelope.get(KEY_EPOCH)
        try:
            msg_epoch_int = int(msg_epoch) if msg_epoch is not None else None
        except (TypeError, ValueError):
            msg_epoch_int = None
        if msg_epoch_int is not None and msg_epoch_int != current_epoch:
            return (
                False,
                None,
                _violation_step_result(COORD_SENDER_NOT_AUTHORIZED, envelope),
            )

        # 4) Message type allowed
        msg_type = envelope.get(KEY_MESSAGE_TYPE) or ""
        if self._allowed_message_types and msg_type not in self._allowed_message_types:
            return (
                False,
                None,
                _violation_step_result(COORD_SENDER_NOT_AUTHORIZED, envelope),
            )

        # 5) Sender authorized
        if self._allowed_senders is not None and sender_id not in self._allowed_senders:
            return (
                False,
                None,
                _violation_step_result(COORD_SENDER_NOT_AUTHORIZED, envelope),
            )

        # 6) High-impact: require countersign (policy hook; we do not verify countersign here, only allow through if not high-impact or caller supplies countersign later)
        if msg_type in self._high_impact_require_countersign:
            countersign = envelope.get("countersign")
            if not countersign:
                return (
                    False,
                    None,
                    _violation_step_result(COORD_SENDER_NOT_AUTHORIZED, envelope),
                )
            # Minimal check: present; full countersign verification can be added later
            pass

        delivered = {
            KEY_SENDER_ID: sender_id,
            KEY_NONCE: nonce_int,
            KEY_EPOCH: envelope.get(KEY_EPOCH),
            KEY_MESSAGE_TYPE: msg_type,
            KEY_PAYLOAD: envelope.get(KEY_PAYLOAD),
        }
        return True, delivered, None


def _violation_step_result(
    reason_code: str,
    envelope: dict[str, Any],
) -> dict[str, Any]:
    """Build step-result fragment for runner: violations + emits (runner output contract)."""
    return {
        "violations": [
            {
                "reason_code": reason_code,
                "invariant_id": reason_code,
                "status": "VIOLATION",
            }
        ],
        "emits": [reason_code],
        "coord_violation_payload": {
            "reason_code": reason_code,
            "sender_id": envelope.get(KEY_SENDER_ID),
            "message_type": envelope.get(KEY_MESSAGE_TYPE),
            "nonce": envelope.get(KEY_NONCE),
        },
    }


def load_coordination_identity_policy(policy_path: Any) -> dict[str, Any]:
    """Load coordination_identity_policy YAML. Returns dict or empty dict on error."""
    from pathlib import Path

    from labtrust_gym.policy.loader import load_yaml

    path = Path(policy_path) if not isinstance(policy_path, Path) else policy_path
    if not path.exists():
        return {}
    data = load_yaml(path)
    root = data.get("coordination_identity_policy") or data
    if isinstance(root, dict):
        return root
    return {}
