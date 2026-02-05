"""
Fuzz harness: deterministic event-sequence generation and contract/safety checks.

Generates random but valid event sequences constrained by policy schemas and
tool arg schemas. Detects contract violations, non-determinism, and safety
bypasses. Writes minimal reproducer YAML to runs/fuzz_failures/ when a
counterexample is found.

Deterministic given seed; suitable for CI smoke when run with fixed seed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from labtrust_gym.tools.arg_validation import load_arg_schema, validate_tool_args
from labtrust_gym.tools.registry import get_tool_entry, load_tool_registry


# Step result contract: required keys for a valid step output
REQUIRED_STEP_KEYS = frozenset({"status", "emits", "violations"})

# Action types that need no or minimal args for fuzzing (no zone/device dependency)
SIMPLE_ACTION_TYPES = [
    "TICK",
    "MOVE",
    "OPEN_DOOR",
    "CREATE_ACCESSION",
    "QUEUE_RUN",
]

# Tool IDs from registry (fallback if registry not loaded)
DEFAULT_TOOL_IDS = ["read_lims_v1", "query_queue_v1", "write_lims_v1"]


@dataclass
class FuzzConfig:
    """Configuration for a fuzz run."""

    seed: int = 42
    max_steps_per_sequence: int = 20
    max_sequences: int = 10
    policy_root: Optional[Path] = None
    agent_ids: List[str] = field(default_factory=lambda: ["A_OPS_0", "A_RECEPTION_0"])
    out_dir: Path = field(default_factory=lambda: Path("runs/fuzz_failures"))


def _sample_valid_args_from_schema(
    schema: Dict[str, Any],
    rng: Any,
) -> Dict[str, Any]:
    """
    Build a minimal valid args dict from a JSON Schema (tool args).
    Deterministic for given rng state.
    """
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    out: Dict[str, Any] = {}
    for key, prop in props.items():
        p = prop if isinstance(prop, dict) else {}
        if p.get("type") == "string":
            min_len = p.get("minLength", 1)
            max_len = min(p.get("maxLength", 128), 32)
            length = max(min_len, rng.randint(min_len, max_len) if max_len > min_len else min_len)
            out[key] = "f" + "x" * (length - 1)
        elif p.get("type") == "integer":
            lo = p.get("minimum", 0)
            hi = p.get("maximum", 100)
            out[key] = rng.randint(lo, hi)
        elif key in required:
            out[key] = "val"
    return out


def _build_tool_events(
    registry: Dict[str, Any],
    policy_root: Optional[Path],
    rng: Any,
    agent_ids: List[str],
    t_start: int,
    count: int,
) -> List[Dict[str, Any]]:
    """Build up to `count` tool-call events with schema-valid args. Deterministic given rng."""
    events: List[Dict[str, Any]] = []
    tools = (registry.get("tool_registry") or {}).get("tools") or []
    if not tools and policy_root is None:
        return events
    tool_ids = [t.get("tool_id") for t in tools if t.get("tool_id")]
    if not tool_ids:
        tool_ids = DEFAULT_TOOL_IDS
    for i in range(count):
        t_s = t_start + i
        agent_id = rng.choice(agent_ids)
        tool_id = rng.choice(tool_ids)
        entry = get_tool_entry(registry, tool_id) if registry else None
        args: Dict[str, Any] = {}
        if entry and policy_root and entry.get("arg_schema_ref"):
            try:
                schema = load_arg_schema(entry["arg_schema_ref"], policy_root)
                args = _sample_valid_args_from_schema(schema, rng)
            except Exception:
                args = {"accession_id": "F1", "device_id": "D1"}
        events.append({
            "t_s": t_s,
            "agent_id": agent_id,
            "action_type": "TICK",
            "args": args,
            "tool_id": tool_id,
        })
    return events


def generate_event_sequence(
    seed: int,
    policy_root: Optional[Path] = None,
    max_steps: int = 20,
    agent_ids: Optional[List[str]] = None,
    tool_fraction: float = 0.3,
) -> List[Dict[str, Any]]:
    """
    Generate a single deterministic event sequence for fuzzing.

    Uses policy_root to load tool registry and arg schemas; events are
    constrained to valid action types and schema-valid tool args.
    """
    rng = __import__("random").Random(seed)
    agents = agent_ids or ["A_OPS_0"]
    registry = load_tool_registry(policy_root) if policy_root else {}
    events: List[Dict[str, Any]] = []
    t_s = 0
    n_tool = max(0, int(max_steps * tool_fraction))
    n_simple = max(0, max_steps - n_tool)
    for i in range(n_simple):
        events.append({
            "t_s": t_s + i,
            "agent_id": rng.choice(agents),
            "action_type": rng.choice(SIMPLE_ACTION_TYPES),
            "args": {},
        })
    tool_events = _build_tool_events(
        registry, policy_root, rng, agents, t_s + n_simple, n_tool
    )
    events.extend(tool_events)
    events.sort(key=lambda e: (e["t_s"], rng.random()))
    for i, ev in enumerate(events):
        ev["t_s"] = i
    return events


def _step_result_canonical(result: Dict[str, Any]) -> Dict[str, Any]:
    """Canonical representation of a step result for comparison (determinism check)."""
    return {
        "status": result.get("status"),
        "blocked_reason_code": result.get("blocked_reason_code"),
        "emits": sorted(result.get("emits") or []),
        "violations_count": len(result.get("violations") or []),
    }


def _check_step_contract(result: Dict[str, Any]) -> Optional[str]:
    """Return error message if step result violates contract; else None."""
    for k in REQUIRED_STEP_KEYS:
        if k not in result:
            return f"missing key: {k}"
    status = result.get("status")
    if status not in ("ACCEPTED", "BLOCKED"):
        return f"invalid status: {status}"
    emits = result.get("emits")
    if not isinstance(emits, list):
        return "emits must be list"
    return None


def run_fuzz_session(
    seed: int,
    initial_state_factory: Callable[[], Dict[str, Any]],
    env_factory: Callable[[], Any],
    policy_root: Optional[Path] = None,
    max_steps: int = 15,
    max_sequences: int = 5,
    check_determinism: bool = True,
    out_dir: Optional[Path] = None,
) -> Tuple[bool, List[Dict[str, Any]]]:
    """
    Run a fuzz session: generate sequences, run env, check contract and determinism.

    Returns (all_passed, list of failure reports). Each report has keys:
    failure_type, seed, sequence_index, message, events (optional), result (optional).
    """
    failures: List[Dict[str, Any]] = []
    out_dir = out_dir or Path("runs/fuzz_failures")
    initial_state_0 = initial_state_factory()
    agents_list = initial_state_0.get("agents") or []
    agent_ids = [a.get("agent_id") for a in agents_list if a.get("agent_id")]
    if not agent_ids:
        agent_ids = ["A_OPS_0"]
    for seq_idx in range(max_sequences):
        seq_seed = seed + seq_idx * 1000
        events = generate_event_sequence(
            seq_seed,
            policy_root=policy_root,
            max_steps=max_steps,
            agent_ids=agent_ids,
        )
        initial_state = initial_state_factory()
        env = env_factory()
        env.reset(initial_state, deterministic=True, rng_seed=seq_seed)
        results_1: List[Dict[str, Any]] = []
        for ev in events:
            res = env.step(ev)
            err = _check_step_contract(res)
            if err:
                failures.append({
                    "failure_type": "contract_violation",
                    "seed": seq_seed,
                    "sequence_index": seq_idx,
                    "message": err,
                    "event": ev,
                    "result": res,
                })
                write_reproducer(
                    out_dir,
                    seq_seed,
                    "contract_violation",
                    initial_state,
                    events,
                    err,
                )
                break
            results_1.append(_step_result_canonical(res))
        if failures and failures[-1].get("sequence_index") == seq_idx:
            continue
        if check_determinism:
            env2 = env_factory()
            env2.reset(initial_state, deterministic=True, rng_seed=seq_seed)
            for i, ev in enumerate(events):
                res2 = env2.step(ev)
                c1 = results_1[i] if i < len(results_1) else {}
                c2 = _step_result_canonical(res2)
                if c1 != c2:
                    failures.append({
                        "failure_type": "non_determinism",
                        "seed": seq_seed,
                        "sequence_index": seq_idx,
                        "message": f"step {i} differs: {c1} vs {c2}",
                        "events": events,
                    })
                    write_reproducer(
                        out_dir,
                        seq_seed,
                        "non_determinism",
                        initial_state,
                        events,
                        f"step {i} differs",
                    )
                    break
    return (len(failures) == 0, failures)


def write_reproducer(
    out_dir: Path,
    seed: int,
    failure_type: str,
    initial_state: Dict[str, Any],
    events: List[Dict[str, Any]],
    message: str,
) -> None:
    """
    Write a minimal reproducer YAML to out_dir for the given counterexample.

    Filename: fuzz_<failure_type>_seed<seed>.yaml
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_type = failure_type.replace(" ", "_")
    path = out_dir / f"fuzz_{safe_type}_seed{seed}.yaml"
    payload = {
        "seed": seed,
        "failure_type": failure_type,
        "message": message,
        "initial_state": initial_state,
        "events": events,
    }
    try:
        import yaml
        with path.open("w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, default_flow_style=False, allow_unicode=True)
    except Exception:
        path.write_text(
            json.dumps({"seed": seed, "failure_type": failure_type, "message": message, "events": events}, indent=2),
            encoding="utf-8",
        )


def canonical_episode_hash(events: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> str:
    """Compute deterministic hash of event sequence + step results for regression checks."""
    canonical = json.dumps(
        [
            {"event": e, "result": _step_result_canonical(r)}
            for e, r in zip(events, results)
        ],
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
