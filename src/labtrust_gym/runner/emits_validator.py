"""
Load and validate emits against the canonical vocabulary. Unknown emits fail tests.

Re-exports from policy.emits so the runner uses the same loader and validator
(policy/emits/emits_vocab.v0.1.yaml canonical_set, PolicyLoadError on invalid files).
"""

from __future__ import annotations

from labtrust_gym.policy.emits import (
    load_emits_vocab,
    validate_emits,
    validate_engine_step_emits,
)

__all__ = ["load_emits_vocab", "validate_emits", "validate_engine_step_emits"]
