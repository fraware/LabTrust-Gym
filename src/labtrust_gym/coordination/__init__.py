"""
Event-sourced blackboard and per-agent views for coordination under partial observability.

BlackboardLog: append-only facts, deterministic ordering, replayable.
ViewReplica: per-agent local view; lags behind global log via CommsModel (delay/drop/reorder).
SignedMessageBus: verify-on-receive, nonce tracking, epoch binding for coordination messages.
"""

from labtrust_gym.coordination.blackboard import (
    BlackboardEvent,
    BlackboardLog,
)
from labtrust_gym.coordination.bus import (
    SignedMessageBus,
    load_coordination_identity_policy,
)
from labtrust_gym.coordination.comms_model import (
    CommsConfig,
    CommsModel,
    Delivery,
)
from labtrust_gym.coordination.identity import (
    COORD_REPLAY_DETECTED,
    COORD_SENDER_NOT_AUTHORIZED,
    COORD_SIGNATURE_INVALID,
    build_key_store,
    sign_message,
    verify_message,
)
from labtrust_gym.coordination.views import ViewReplica

__all__ = [
    "BlackboardEvent",
    "BlackboardLog",
    "ViewReplica",
    "CommsConfig",
    "CommsModel",
    "Delivery",
    "build_key_store",
    "sign_message",
    "verify_message",
    "COORD_SIGNATURE_INVALID",
    "COORD_REPLAY_DETECTED",
    "COORD_SENDER_NOT_AUTHORIZED",
    "SignedMessageBus",
    "load_coordination_identity_policy",
]
