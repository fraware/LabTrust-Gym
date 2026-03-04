"""
Record and replay coordination (proposal/bid) fixtures for llm_offline.

Key: method_id + "/" + SHA-256(canonical JSON of state_digest, step_id,
method_id, allowed_actions). Value: JSON with "proposal" and "meta".
File: coordination_fixtures.json under fixtures_dir.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.llm.fault_model_coord import _coord_input_digest


def coord_fixture_key(
    state_digest: dict[str, Any],
    step_id: int,
    method_id: str,
    allowed_actions: list[str] | None = None,
) -> str:
    """Key for coordination fixture: method_id/digest_hex."""
    digest = _coord_input_digest(state_digest, step_id, method_id, allowed_actions)
    return f"{method_id}/{digest}"


def merge_and_write_coord_fixtures(
    new_records: dict[str, str],
    fixtures_dir: Path,
) -> int:
    """
    Merge new_records into coordination_fixtures.json under fixtures_dir.
    Returns total number of keys after merge.
    """
    path = fixtures_dir / "coordination_fixtures.json"
    existing: dict[str, str] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            resp = data.get("responses")
            if isinstance(resp, dict):
                existing = {k: str(v) for k, v in resp.items()}
        except (json.JSONDecodeError, OSError):
            pass
    existing.update(new_records)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "responses": existing,
        "_comment": ("Keys: method_id/digest_hex. Add via record-coordination-fixtures."),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return len(existing)


class RecordingProposalBackend:
    """
    Wraps a proposal or bid backend; records each (key, response) for
    coordination_fixtures.json. Key = coord_fixture_key(...).
    """

    def __init__(
        self,
        inner: Any,
        method_id: str,
        records: dict[str, str] | None = None,
    ) -> None:
        self._inner = inner
        self._method_id = method_id
        self._records = records if records is not None else {}

    def reset(self, seed: int) -> None:
        if hasattr(self._inner, "reset"):
            self._inner.reset(seed)

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str] | None = None,
        step_id: int = 0,
        method_id: str | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        mid = method_id if method_id is not None else self._method_id
        gen = getattr(self._inner, "generate_proposal", None)
        if not callable(gen):
            return ({}, {})
        try:
            raw = gen(
                state_digest=state_digest,
                allowed_actions=allowed_actions,
                step_id=step_id,
                method_id=mid,
                **kwargs,
            )
        except TypeError:
            raw = gen(
                state_digest=state_digest,
                step_id=step_id,
                method_id=mid,
                **{k: v for k, v in kwargs.items() if k != "allowed_actions"},
            )
        if isinstance(raw, tuple):
            proposal, meta = raw[0], raw[1]
        else:
            proposal = raw
            meta = proposal.get("meta") if isinstance(proposal, dict) else {}
        key = coord_fixture_key(state_digest, step_id, mid, allowed_actions)
        self._records[key] = json.dumps({"proposal": proposal, "meta": meta or {}}, sort_keys=True)
        return (proposal, meta or {})

    @property
    def records(self) -> dict[str, str]:
        return dict(self._records)


class FixtureProposalBackend:
    """
    Offline coordination backend: lookup (proposal, meta) by
    coord_fixture_key. Raises FixtureMissingError when key is missing.
    """

    def __init__(
        self,
        fixtures_dir: Path,
        method_id: str,
    ) -> None:
        self._fixtures_dir = Path(fixtures_dir)
        self._method_id = method_id
        self._cache: dict[str, str] | None = None

    def _load_responses(self) -> dict[str, str]:
        if self._cache is not None:
            return self._cache
        path = self._fixtures_dir / "coordination_fixtures.json"
        if not path.exists():
            self._cache = {}
            return self._cache
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            resp = data.get("responses")
            if not isinstance(resp, dict):
                self._cache = {}
                return self._cache
            self._cache = {k: str(v) for k, v in resp.items()}
            return self._cache
        except (json.JSONDecodeError, OSError):
            self._cache = {}
            return self._cache

    def reset(self, seed: int) -> None:
        pass

    def generate_proposal(
        self,
        state_digest: dict[str, Any],
        allowed_actions: list[str] | None = None,
        step_id: int = 0,
        method_id: str | None = None,
        **kwargs: Any,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        mid = method_id if method_id is not None else self._method_id
        key = coord_fixture_key(state_digest, step_id, mid, allowed_actions)
        responses = self._load_responses()
        if key not in responses:
            from labtrust_gym.baselines.llm.exceptions import FixtureMissingError

            raise FixtureMissingError(
                f"No coordination fixture for {key[:32]}...; run with record-coordination-fixtures to capture.",
                key=key,
                remediation=("Run record-coordination-fixtures with network enabled."),
            )
        parsed = json.loads(responses[key])
        proposal = parsed.get("proposal", {})
        meta = parsed.get("meta", {})
        return (proposal, meta)
