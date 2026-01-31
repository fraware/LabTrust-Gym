"""
LLM agent interface: offline-safe and deterministic by default.

- LLMBackend protocol: generate(messages) -> text
- LLMAgent: system prompt, backend call, strict JSON parse + schema validation
- MockDeterministicBackend: canned JSON from observation hash (deterministic)
- OpenAIBackend stub: API key from env; not used in tests
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple

# Action indices aligned with pz_parallel
ACTION_NOOP = 0
ACTION_TICK = 1
ACTION_QUEUE_RUN = 2
ACTION_MOVE = 3
ACTION_OPEN_DOOR = 4
ACTION_START_RUN = 5


def _obs_hash(obs: Dict[str, Any]) -> str:
    """Stable hash of observation for deterministic mock lookup."""
    def _enc(o: Any) -> Any:
        if hasattr(o, "tolist"):
            return o.tolist()
        if isinstance(o, dict):
            return {k: _enc(v) for k, v in sorted(o.items())}
        if isinstance(o, list):
            return [_enc(x) for x in o]
        return o
    return hashlib.sha256(
        json.dumps(_enc(obs), sort_keys=True).encode()
    ).hexdigest()


class LLMBackend(Protocol):
    """Protocol: generate(messages) -> text."""

    def generate(self, messages: List[Dict[str, str]]) -> str:
        """Return raw text (must be parseable as strict JSON action)."""
        ...


class MockDeterministicBackend:
    """
    Deterministic backend: returns canned JSON actions keyed by observation hash.
    Offline-safe; no API calls.
    """

    def __init__(
        self,
        canned: Optional[Dict[str, Dict[str, Any]]] = None,
        default_action_type: int = ACTION_NOOP,
    ) -> None:
        self._canned = canned or {}
        self._default = default_action_type

    def generate(self, messages: List[Dict[str, str]]) -> str:
        """Ignore messages; use last user message or placeholder to derive hash, or default."""
        user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        h = hashlib.sha256(user.encode()).hexdigest()[:16]
        entry = self._canned.get(h)
        if entry is not None:
            return json.dumps(entry, sort_keys=True)
        return json.dumps({
            "action_type": self._default,
            "action_info": {},
        }, sort_keys=True)


class OpenAIBackend:
    """
    Stub backend: reads API key from OPENAI_API_KEY; never used in tests.
    Real implementation would call OpenAI API.
    """

    def __init__(self, api_key_env: str = "OPENAI_API_KEY") -> None:
        import os
        self._api_key = os.environ.get(api_key_env, "")

    def generate(self, messages: List[Dict[str, str]]) -> str:
        """Stub: returns NOOP if no key; otherwise would call API."""
        if not self._api_key:
            return json.dumps({"action_type": ACTION_NOOP, "action_info": {}}, sort_keys=True)
        raise NotImplementedError("OpenAI API call not implemented in this stub")


def load_action_schema(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load action schema JSON for validation."""
    path = path or Path("policy/llm/action_schema.v0.1.json")
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def validate_action_against_schema(
    action: Dict[str, Any],
    schema: Dict[str, Any],
) -> List[str]:
    """Validate action dict against JSON schema. Returns list of error strings."""
    if not schema:
        return []
    try:
        import jsonschema
        jsonschema.validate(instance=action, schema=schema)
        return []
    except jsonschema.ValidationError as e:
        return [str(e)]
    except Exception as e:
        return [str(e)]


def _default_system_prompt() -> str:
    return (
        "You are a lab operations agent. Output a single JSON object with keys: "
        "action_type (0=NOOP, 1=TICK, 2=QUEUE_RUN, 3=MOVE, 4=OPEN_DOOR, 5=START_RUN) "
        "and optional action_info (device_id, work_id, priority, to_zone, door_id, token_refs). "
        "No other text. Constraints: do not open restricted doors without token; do not queue when log_frozen."
    )


class LLMAgent:
    """
    Agent that uses an LLM backend to choose actions.
    Builds system prompt, calls backend, parses strict JSON, validates against schema.
    """

    def __init__(
        self,
        backend: LLMBackend,
        schema_path: Optional[Path] = None,
        system_prompt: Optional[str] = None,
    ) -> None:
        self._backend = backend
        self._schema = load_action_schema(schema_path)
        self._system_prompt = system_prompt or _default_system_prompt()

    def act(
        self,
        observation: Dict[str, Any],
        agent_id: str = "ops_0",
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Return (action_index, action_info). Calls backend, parses JSON, validates.
        On parse or validation failure, returns (ACTION_NOOP, {}).
        """
        user_content = json.dumps(_obs_hash(observation))  # or a summary of obs
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": user_content},
        ]
        text = self._backend.generate(messages)
        text = text.strip()
        if "```" in text:
            for part in text.split("```"):
                part = part.strip()
                if part.startswith("json") or part.startswith("{"):
                    text = part.replace("json", "", 1).strip()
                    break
        try:
            action = json.loads(text)
        except json.JSONDecodeError:
            return (ACTION_NOOP, {})
        if not isinstance(action, dict):
            return (ACTION_NOOP, {})
        errs = validate_action_against_schema(action, self._schema)
        if errs:
            return (ACTION_NOOP, {})
        action_type = int(action.get("action_type", ACTION_NOOP))
        if action_type < 0 or action_type > 5:
            action_type = ACTION_NOOP
        action_info = action.get("action_info")
        if not isinstance(action_info, dict):
            action_info = {}
        return (action_type, action_info)
