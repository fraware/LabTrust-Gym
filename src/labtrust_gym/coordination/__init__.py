"""
Coordination layer: blackboard, views, and signed message bus.

BlackboardLog holds append-only facts with deterministic ordering (replayable).
ViewReplica gives each agent a local view that may lag behind the global log
via CommsModel (delay, drop, reorder). SignedMessageBus verifies messages on
receive, tracks nonces, and binds messages to an epoch for replay-safe
coordination traffic.
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
