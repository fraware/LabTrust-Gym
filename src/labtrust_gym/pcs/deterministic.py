"""Fixture-only deterministic PCS artifact generation (goldens, CI)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

from labtrust_gym.version import __version__

# Frozen provenance for committed golden artifacts (not used in normal runs).
DETERMINISTIC_SOURCE_COMMIT = "c20139460f7e46b0fe3031e9da70a1c36e4dda33"
DETERMINISTIC_ENVIRONMENT = {
    "platform": "pcs-golden-fixture",
    "python": "3.11.0",
    "labtrust_version": __version__,
}
DETERMINISTIC_CERTIFICATE_ID = "cert-trace-pcs-qc-release-v0.1"
DETERMINISTIC_CERT_SOURCE_COMMIT = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
DETERMINISTIC_CERT_DIGEST = "sha256:" + "a" * 64

_pcs_deterministic: ContextVar[bool] = ContextVar("pcs_deterministic", default=False)


def is_deterministic_mode() -> bool:
    if _pcs_deterministic.get():
        return True
    return os.environ.get("PCS_DETERMINISTIC", "").strip().lower() in ("1", "true", "yes")


@contextmanager
def deterministic_mode(*, enabled: bool = True) -> Iterator[None]:
    """Enable deterministic PCS fields for the current context."""
    token = _pcs_deterministic.set(enabled)
    try:
        yield
    finally:
        _pcs_deterministic.reset(token)
