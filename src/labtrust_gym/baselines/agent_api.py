"""
External agent plugin interface and dynamic loader.

Researchers can run an agent baseline by pointing to "module:Class" or
"module:function" without modifying core code. LabTrustAgent protocol:
reset(seed, policy_summary, partner_id, timing_mode); act(observation) -> action (int);
optional explain_last_action() -> dict; optional healthcheck() -> bool; optional warm_up().
Contract version: AGENT_CONTRACT_VERSION (e.g. v0.1) for compatibility checks.
"""

from __future__ import annotations

import importlib
import inspect
import re
import sys
from pathlib import Path
from typing import Any, Protocol

# Versioned agent contract; bump when breaking changes to reset/act/explain_last_action.
AGENT_CONTRACT_VERSION = "0.1"


class ContractVersionMismatch(ValueError):
    """Raised when a loaded agent reports a contract_version incompatible with expected."""

    def __init__(
        self,
        expected: str,
        actual: str,
        spec: str,
    ) -> None:
        self.expected = expected
        self.actual = actual
        self.spec = spec
        super().__init__(
            f"Agent contract version mismatch: spec={spec!r} reports "
            f"contract_version={actual!r}, runner expects {expected!r}. "
            "Update the agent or AGENT_CONTRACT_VERSION."
        )


class LabTrustAgent(Protocol):
    """Protocol for external agents loadable via module:Class or module:function."""

    def reset(
        self,
        seed: int,
        policy_summary: dict[str, Any] | None = None,
        partner_id: str | None = None,
        timing_mode: str = "explicit",
    ) -> None:
        """Called at the start of each episode. Optional; no-op if not implemented."""
        ...

    def act(self, observation: dict[str, Any]) -> int | tuple[int, dict[str, Any]]:
        """
        Return action (discrete index) or (action, action_info).
        observation is the per-agent obs dict from the env.
        """
        ...

    def explain_last_action(self) -> dict[str, Any] | None:
        """Optional: return dict with action_type, args, etc. for logging. None if not implemented."""
        ...


# Optional extensions (not part of Protocol): healthcheck() -> bool, warm_up(observation).
# Wrapper exposes them and delegates to inner when present.

# Pattern: module.path:ClassName or module.path:function_name
_AGENT_SPEC_PATTERN = re.compile(r"^([a-zA-Z_][a-zA-Z0-9_.]*):([a-zA-Z_][a-zA-Z0-9_]*)$")


def load_agent(
    spec: str,
    repo_root: Path | None = None,
    expect_contract_version: str | None = None,
) -> Any:
    """
    Load an agent from spec "module:ClassName" or "module:function_name".

    - module:ClassName -> instantiate ClassName() (no args)
    - module:function_name -> call function() and return result (factory)
    - If the loaded instance has a contract_version attribute, it must match
      expect_contract_version or AGENT_CONTRACT_VERSION; else ContractVersionMismatch.

    If module_path starts with "examples." and import fails, repo_root (or cwd)
    is prepended to sys.path so examples/ is loadable when run from repo root.

    Raises:
        ValueError: invalid spec format
        ContractVersionMismatch: agent contract_version != expected
        ModuleNotFoundError: module not found
        AttributeError: class or function not found in module
        TypeError: instantiation/call failed
    """
    spec = (spec or "").strip()
    if not spec:
        raise ValueError("Invalid agent spec (empty); use 'module:ClassName' or 'module:function'")
    m = _AGENT_SPEC_PATTERN.match(spec)
    if not m:
        raise ValueError(
            f"Invalid agent spec {spec!r}; expected 'module.path:ClassName' or 'module.path:function_name'"
        )
    module_path, name = m.group(1), m.group(2)
    try:
        mod = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        if module_path.startswith("examples.") and repo_root is None:
            repo_root = Path.cwd()
        if module_path.startswith("examples.") and repo_root is not None:
            root = Path(repo_root).resolve()
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            try:
                mod = importlib.import_module(module_path)
            except ModuleNotFoundError as e2:
                raise ModuleNotFoundError(f"Agent module {module_path!r} not found: {e2}") from e2
        else:
            raise ModuleNotFoundError(f"Agent module {module_path!r} not found: {e}") from e
    obj = getattr(mod, name, None)
    if obj is None:
        raise AttributeError(f"Module {module_path!r} has no attribute {name!r}")
    if callable(obj):
        try:
            sig = inspect.signature(obj)
            if repo_root is not None and "repo_root" in sig.parameters:
                instance = obj(repo_root=repo_root)
            else:
                instance = obj()
        except Exception as e:
            raise TypeError(f"Failed to instantiate/call {module_path!r}:{name!r}: {e}") from e
        expected_ver = expect_contract_version or AGENT_CONTRACT_VERSION
        actual = getattr(instance, "contract_version", None)
        if actual is not None and str(actual).strip() != str(expected_ver).strip():
            raise ContractVersionMismatch(
                expected=expected_ver,
                actual=str(actual),
                spec=spec,
            )
        return instance
    raise TypeError(
        f"Agent spec {module_path!r}:{name!r} is not callable "
        "(expected class or factory function)"
    )


def wrap_agent_for_runner(agent: Any) -> Any:
    """
    Wrap a LabTrustAgent (or any with act, optional reset/explain_last_action/healthcheck/warm_up)
    for use in scripted_agents_map: act(obs, agent_id) -> (action_index, action_info, meta).
    Exposes contract_version and optional healthcheck/warm_up for state-of-the-art pipelines.
    """

    class Wrapper:
        def __init__(self, inner: Any) -> None:
            self._inner = inner
            self._last_info: dict[str, Any] = {}

        @property
        def contract_version(self) -> str:
            return AGENT_CONTRACT_VERSION

        def healthcheck(self) -> bool:
            fn = getattr(self._inner, "healthcheck", None)
            if callable(fn):
                return bool(fn())
            return True

        def warm_up(self, observation: dict[str, Any] | None = None) -> None:
            fn = getattr(self._inner, "warm_up", None)
            if callable(fn):
                fn(observation)
                return
            if observation is not None and hasattr(self._inner, "act"):
                self._inner.act(observation)

        def reset(
            self,
            seed: int,
            policy_summary: dict[str, Any] | None = None,
            partner_id: str | None = None,
            timing_mode: str = "explicit",
        ) -> None:
            fn = getattr(self._inner, "reset", None)
            if callable(fn):
                fn(seed, policy_summary, partner_id, timing_mode)

        def act(self, observation: dict[str, Any], agent_id: str = "") -> tuple[int, dict[str, Any], dict[str, Any]]:
            out = self._inner.act(observation)
            if isinstance(out, tuple):
                action_idx = int(out[0])
                action_info = dict(out[1]) if len(out) > 1 and isinstance(out[1], dict) else {}
            else:
                action_idx = int(out)
                action_info = {}
            self._last_info = action_info
            meta = {}
            explain = getattr(self._inner, "explain_last_action", None)
            if callable(explain):
                ex = explain()
                if isinstance(ex, dict):
                    meta = ex
            return (action_idx, action_info, meta)

    return Wrapper(agent)
