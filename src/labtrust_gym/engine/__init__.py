"""
Core simulation engine: state, events, clock, zones, devices, audit log, tokens.

This package holds the minimal engine (CoreEnv), typed shapes for reset/step
(InitialStateDict, StepEventDict), and supporting stores (AuditLog, TokenStore).
Other engine submodules (zones, specimens, queueing, qc, critical, etc.) are
used by CoreEnv but not re-exported here.
"""

from labtrust_gym.engine.audit_log import (
    AuditLog,
    canonical_serialize,
    hash_event,
)
from labtrust_gym.engine.core_env import CoreEnv
from labtrust_gym.engine.errors import (
    AUDIT_CHAIN_BROKEN,
    INV_TOK_001,
    RC_INJECT_SPECIMEN_DUPLICATE,
)
from labtrust_gym.engine.event import StepEventDict
from labtrust_gym.engine.state import InitialStateDict
from labtrust_gym.engine.tokens_runtime import TokenStore

__all__ = [
    "AUDIT_CHAIN_BROKEN",
    "INV_TOK_001",
    "RC_INJECT_SPECIMEN_DUPLICATE",
    "AuditLog",
    "CoreEnv",
    "InitialStateDict",
    "StepEventDict",
    "TokenStore",
    "canonical_serialize",
    "hash_event",
]
