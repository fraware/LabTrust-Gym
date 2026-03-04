"""
Determinism tests for inj_dos_flood, inj_memory_tamper, inj_tool_selection_noise.
Same seed => same mutation trace (hash of applied steps).
"""

from __future__ import annotations

import hashlib
import json

from labtrust_gym.security.risk_injections import make_injector


def _signature_messages(seed: int, injection_id: str, steps: int = 15) -> str:
    """Hash of mutate_messages trace (for inj_dos_flood)."""
    inj = make_injector(injection_id, intensity=0.7, seed_offset=0)
    inj.reset(seed, None)
    messages = [{"payload": f"msg_{i}", "from": "a"} for i in range(3)]
    recs = []
    for _ in range(steps):
        out, audit = inj.mutate_messages(messages)
        recs.append(json.dumps({"len": len(out), "audit": audit is not None}, sort_keys=True))
        messages = out
        inj.observe_step([])
    return hashlib.sha256("\n".join(recs).encode()).hexdigest()


def _signature_obs(seed: int, injection_id: str, steps: int = 15) -> str:
    """Hash of mutate_obs trace (for inj_memory_tamper)."""
    inj = make_injector(injection_id, intensity=0.7, seed_offset=0)
    inj.reset(seed, None)
    obs = {"agent_0": {"x": 1}, "agent_1": {"x": 2}}
    recs = []
    for _ in range(steps):
        out, audit = inj.mutate_obs(obs)
        recs.append(json.dumps({"audit": audit is not None, "tamper": "_memory_tamper" in str(out)}, sort_keys=True))
        obs = out
        inj.observe_step([])
    return hashlib.sha256("\n".join(recs).encode()).hexdigest()


def _signature_actions(seed: int, injection_id: str, steps: int = 15) -> str:
    """Hash of mutate_actions trace (for inj_tool_selection_noise)."""
    inj = make_injector(injection_id, intensity=0.8, seed_offset=0)
    inj.reset(seed, None)
    actions = {
        "a0": {"action_index": 3, "tool_id": "CREATE_ACCESSION", "args": {"specimen_id": "S1"}},
        "a1": {"action_index": 2},
    }
    recs = []
    for _ in range(steps):
        out, audit_list = inj.mutate_actions(actions)
        recs.append(json.dumps({"n_audit": len(audit_list), "keys": sorted(out.keys())}, sort_keys=True))
        actions = out
        inj.observe_step([])
    return hashlib.sha256("\n".join(recs).encode()).hexdigest()


def test_inj_dos_flood_deterministic() -> None:
    """Same seed => same mutate_messages trace for inj_dos_flood."""
    h1 = _signature_messages(42, "inj_dos_flood")
    h2 = _signature_messages(42, "inj_dos_flood")
    assert h1 == h2


def test_inj_memory_tamper_deterministic() -> None:
    """Same seed => same mutate_obs trace for inj_memory_tamper."""
    h1 = _signature_obs(42, "inj_memory_tamper")
    h2 = _signature_obs(42, "inj_memory_tamper")
    assert h1 == h2


def test_inj_tool_selection_noise_deterministic() -> None:
    """Same seed => same mutate_actions trace for inj_tool_selection_noise."""
    h1 = _signature_actions(42, "inj_tool_selection_noise")
    h2 = _signature_actions(42, "inj_tool_selection_noise")
    assert h1 == h2
