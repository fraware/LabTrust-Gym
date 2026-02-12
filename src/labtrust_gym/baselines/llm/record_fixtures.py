"""
Record LLM fixtures from live OpenAI responses (offline-friendly design).

Run manually with network enabled (not in CI) to populate
tests/fixtures/llm_responses/ so that deterministic pipeline can use
FixtureBackend without network.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from labtrust_gym.baselines.llm.agent import _messages_digest


class RecordingBackend:
    """
    Wraps an LLMBackend and records each (messages_digest, response)
    for fixture writing.
    """

    def __init__(self, inner: Any, records: dict[str, str] | None = None) -> None:
        self._inner = inner
        self._records = records if records is not None else {}

    def generate(self, messages: list[dict[str, str]]) -> str:
        key = _messages_digest(messages)
        response = self._inner.generate(messages)
        self._records[key] = response
        return response

    @property
    def records(self) -> dict[str, str]:
        return dict(self._records)


def merge_and_write_fixtures(
    new_records: dict[str, str],
    fixtures_dir: Path,
) -> int:
    """
    Merge new_records into fixtures.json under fixtures_dir; write back.
    Returns number of keys written (existing + new).
    """
    path = fixtures_dir / "fixtures.json"
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
        "_comment": (
            "Keys are SHA-256 of canonical JSON messages. "
            "Add entries via record-llm-fixtures."
        ),
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return len(existing)
