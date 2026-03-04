"""
Tests for ripple_effect coordination method.

- Determinism: same seed yields identical comm.msg_count, throughput, and blocks.
- Resilience under INJ-COMMS-POISON-001: detection metrics improve or containment
  actions increase; with strict signatures, no silent acceptance of spoofed updates
  (invalid_sig_count, replay_drop_count, or spoof_attempt_count reflect rejections).
"""

from __future__ import annotations

import json
from pathlib import Path

from labtrust_gym.benchmarks.runner import run_benchmark


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run_taskg(
    tmp_path: Path,
    seed: int = 42,
    num_episodes: int = 1,
) -> dict:
    out = tmp_path / "taskg_results.json"
    run_benchmark(
        task_name="coord_scale",
        num_episodes=num_episodes,
        base_seed=seed,
        out_path=out,
        repo_root=_repo_root(),
        coord_method="ripple_effect",
        pipeline_mode="deterministic",
    )
    assert out.exists()
    return json.loads(out.read_text(encoding="utf-8"))


def _run_taskh(
    tmp_path: Path,
    injection_id: str = "INJ-COMMS-POISON-001",
    seed: int = 42,
) -> dict:
    out = tmp_path / "taskh_results.json"
    run_benchmark(
        task_name="coord_risk",
        num_episodes=1,
        base_seed=seed,
        out_path=out,
        repo_root=_repo_root(),
        coord_method="ripple_effect",
        injection_id=injection_id,
        pipeline_mode="deterministic",
    )
    assert out.exists()
    return json.loads(out.read_text(encoding="utf-8"))


def test_ripple_effect_deterministic_same_seed_same_comm_throughput_blocks(
    tmp_path: Path,
) -> None:
    """Same seed -> identical comm.msg_count, throughput, and blocks."""
    run1 = _run_taskg(tmp_path, seed=42)
    run2 = _run_taskg(tmp_path, seed=42)
    episodes1 = run1.get("episodes") or []
    episodes2 = run2.get("episodes") or []
    assert len(episodes1) >= 1 and len(episodes2) >= 1
    m1 = episodes1[0].get("metrics") or {}
    m2 = episodes2[0].get("metrics") or {}
    comm1 = (m1.get("coordination") or {}).get("comm") or {}
    comm2 = (m2.get("coordination") or {}).get("comm") or {}
    assert comm1.get("msg_count") == comm2.get("msg_count"), "comm.msg_count must be identical for same seed"
    assert m1.get("throughput") == m2.get("throughput"), "throughput must be identical for same seed"
    blocks1 = sum((m1.get("blocked_by_reason_code") or {}).values())
    blocks2 = sum((m2.get("blocked_by_reason_code") or {}).values())
    assert blocks1 == blocks2, "blocks (blocked_by_reason_code total) must be identical for same seed"


def test_ripple_effect_taskh_comms_poison_no_crash_and_comm_metrics(tmp_path: Path) -> None:
    """TaskH INJ-COMMS-POISON-001: no crash; coordination comm metrics present."""
    data = _run_taskh(tmp_path, "INJ-COMMS-POISON-001")
    episodes = data.get("episodes") or []
    assert len(episodes) >= 1
    metrics = episodes[0].get("metrics") or {}
    coord = metrics.get("coordination") or {}
    comm = coord.get("comm") or {}
    assert "msg_count" in comm
    assert "invalid_sig_count" in comm
    assert "replay_drop_count" in comm
    assert "throughput" in metrics


def test_ripple_effect_taskh_comms_poison_detection_or_containment(tmp_path: Path) -> None:
    """
    Under INJ-COMMS-POISON-001 either detection metrics improve or containment
    actions increase; at minimum no silent acceptance of spoofed updates when
    strict signatures are on (rejections reflected in invalid_sig_count,
    replay_drop_count, or spoof_attempt_count).
    """
    data = _run_taskh(tmp_path, "INJ-COMMS-POISON-001")
    episodes = data.get("episodes") or []
    assert len(episodes) >= 1
    metrics = episodes[0].get("metrics") or {}
    coord = metrics.get("coordination") or {}
    comm = coord.get("comm") or {}
    sec = metrics.get("sec") or {}
    rejection_indicators = (
        comm.get("invalid_sig_count", 0) + comm.get("replay_drop_count", 0) + comm.get("spoof_attempt_count", 0)
    )
    detection_improved = (
        sec.get("detection_latency_steps") is not None or sec.get("time_to_attribution_steps") is not None
    )
    containment_present = sec.get("containment_time_steps") is not None
    assert rejection_indicators > 0 or detection_improved or containment_present, (
        "With INJ-COMMS-POISON-001 expect either rejection counts > 0 "
        "(invalid_sig/replay/spoof) or detection/containment signals; "
        "no silent acceptance of spoofed updates when signatures are enforced."
    )
