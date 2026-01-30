"""
Load and validate emits against the canonical vocabulary.

- Loads allowed emits from policy/emits/emits_vocab.v0.1.yaml (canonical_set).
- Validates engine step outputs: every emit in result.emits must be in allowed set.
  Unknown emits raise AssertionError (used by GoldenRunner).
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Set

from labtrust_gym.policy.loader import PolicyLoadError, load_yaml


def load_emits_vocab(path: str | Path) -> Set[str]:
    """
    Load the canonical emit set from YAML.
    Path may be relative to cwd or absolute. Returns set of allowed emit strings.
    """
    p = Path(path)
    if not p.is_absolute():
        p = Path.cwd() / p
    try:
        data = load_yaml(p)
    except PolicyLoadError:
        raise
    vocab = data.get("emits_vocab")
    if vocab is None:
        raise PolicyLoadError(p, "missing top-level key 'emits_vocab'")
    canonical = vocab.get("canonical_set")
    if canonical is None:
        raise PolicyLoadError(p, "emits_vocab.canonical_set missing")
    if not isinstance(canonical, list):
        raise PolicyLoadError(
            p,
            f"emits_vocab.canonical_set must be a list, got {type(canonical).__name__}",
        )  # noqa: E501
    return set(str(x) for x in canonical)


def validate_emits(
    emits: List[str],
    allowed: Set[str],
    *,
    event_id: str = "",
) -> None:
    """
    Raise AssertionError if any emit is not in the allowed vocabulary.
    Used to validate engine step result.emits.
    """
    unknown = [e for e in emits if e not in allowed]
    if unknown:
        msg = f"[{event_id}] unknown emits: {unknown} | allowed={sorted(allowed)}"
        raise AssertionError(msg)


def validate_engine_step_emits(
    result: dict,
    allowed: Set[str],
    *,
    event_id: str = "",
) -> None:
    """
    Validate result["emits"] from an engine step against the allowed set.
    Raises AssertionError if any emit is unknown.
    """
    emits = result.get("emits", [])
    validate_emits(emits, allowed, event_id=event_id)
