"""
Dedicated error types for LabTrust-Gym.

- LabTrustError: base exception for all library-raised errors.
- PolicyLoadError: policy file load/validation failure.
- PolicyPathError: policy/repo root resolution failure.
"""

from __future__ import annotations

from pathlib import Path


class LabTrustError(Exception):
    """Base exception for LabTrust-Gym. All library errors subclass this."""

    pass


class PolicyLoadError(LabTrustError):
    """Policy file load/validation failure. Message includes path."""

    def __init__(self, path: Path | str, message: str) -> None:
        self.path = Path(path) if isinstance(path, str) else path
        super().__init__(f"{self.path}: {message}")


class PolicyPathError(LabTrustError):
    """Raised when policy dir or repo root cannot be resolved (missing or invalid path)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
