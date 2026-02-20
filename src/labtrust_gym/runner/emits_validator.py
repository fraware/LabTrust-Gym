"""
Load and validate step emits against the policy emit vocabulary.

Re-exports load_emits_vocab and validate_emits from policy.emits. The golden
runner and engine use this so that every emit string in step output is checked
against policy/emits/emits_vocab.v0.1.yaml; unknown emits cause validation failure.
"""

from __future__ import annotations

from labtrust_gym.policy.emits import (
    load_emits_vocab,
    validate_emits,
    validate_engine_step_emits,
)

__all__ = ["load_emits_vocab", "validate_emits", "validate_engine_step_emits"]
