"""
Tests for the coordination security pack: outputs (pack_results/, pack_summary.csv, pack_gate.md)
and gate verdicts. Uses mocked run_benchmark to avoid full matrix runs in CI.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from labtrust_gym.studies.coordination_security_pack import (
    PACK_INJECTIONS,
    PACK_METHODS,
    PACK_SCALES,
    _load_pack_config,
    _resolve_methods,
    run_coordination_security_pack,
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _parse_cell_id(cell_id: str) -> tuple[str, str, str]:
    """Parse cell_id into (scale_id, method_id, injection_id). Match longer names first."""
    scales_ordered = sorted(PACK_SCALES, key=len, reverse=True)
    methods_ordered = sorted(PACK_METHODS, key=len, reverse=True)
    for scale_id in scales_ordered:
        if cell_id.startswith(scale_id + "_"):
            rest = cell_id[len(scale_id) + 1 :]
            for method_id in methods_ordered:
                if rest.startswith(method_id + "_"):
                    inj_part = rest[len(method_id) + 1 :]
                    injection_id = inj_part.replace("_", "-")
                    return (scale_id, method_id, injection_id)
            return (scale_id, "", rest.replace("_", "-"))
    return ("small_smoke", "", cell_id.replace("_", "-"))


def _minimal_results_json(scale_id: str, method_id: str, injection_id: str) -> dict:
    """Minimal results.json so aggregation and gate logic can run."""
    return {
        "task": "coord_risk",
        "num_episodes": 1,
        "episodes": [
            {
                "seed": 42,
                "metrics": {
                    "throughput": 1,
                    "violations_by_invariant_id": {},
                    "blocked_by_reason_code": {},
                    "sec": {
                        "attack_success_rate": 0.0 if injection_id == "INJ-ID-SPOOF-001" else None,
                        "detection_latency_steps": None,
                    },
                },
            }
        ],
        "coordination": {"scale_id": scale_id, "method_id": method_id},
        "security": {"injection_id": injection_id},
    }


@pytest.fixture
def repo_root() -> Path:
    return _repo_root()


def test_coordination_security_pack_outputs(repo_root: Path, tmp_path: Path) -> None:
    """Run pack with mocked run_benchmark; assert pack_results/, pack_summary.csv, pack_gate.md."""

    def fake_run_benchmark(
        task_name: str,
        num_episodes: int,
        base_seed: int,
        out_path: Path,
        repo_root: Path,
        coord_method: str,
        injection_id: str,
        scale_config_override: Any,
        **kwargs: Any,
    ) -> None:
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cell_id = out_path.parent.name
        scale_id, method_id, inj_id = _parse_cell_id(cell_id)
        if not method_id:
            method_id = coord_method
        if not inj_id:
            inj_id = injection_id
        data = _minimal_results_json(scale_id, method_id, inj_id)
        out_path.write_text(json.dumps(data), encoding="utf-8")

    import labtrust_gym.studies.coordination_security_pack as pack_mod

    with patch.object(pack_mod, "run_benchmark", side_effect=fake_run_benchmark):
        out_dir = tmp_path / "pack_out"
        run_coordination_security_pack(out_dir=out_dir, repo_root=repo_root, seed_base=42)
        pack_results = out_dir / "pack_results"
        assert pack_results.is_dir()
        cells = [d for d in pack_results.iterdir() if d.is_dir()]
        summary_path = out_dir / "pack_summary.csv"
        assert summary_path.is_file()
        with summary_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            rows = list(reader)
        expected_cells = len(rows)
        assert len(cells) == expected_cells, f"expected {expected_cells} cell dirs (got {len(cells)})"
        for c in cells:
            assert (c / "results.json").is_file()
        for col in ["method_id", "scale_id", "injection_id", "safety.violations_total"]:
            assert col in fieldnames, f"missing column {col}"

        gate_path = out_dir / "pack_gate.md"
        assert gate_path.is_file()
        gate_text = gate_path.read_text(encoding="utf-8")
        assert "PASS" in gate_text
        assert "|" in gate_text
        assert "not_supported" in gate_text or "SKIP" in gate_text or "PASS" in gate_text


def test_coordination_security_pack_gate_verdicts_present(repo_root: Path, tmp_path: Path) -> None:
    """After running pack (mocked), pack_gate.md contains verdict column and expected injection ids."""

    def fake_run_benchmark(
        task_name: str,
        num_episodes: int,
        base_seed: int,
        out_path: Path,
        repo_root: Path,
        coord_method: str,
        injection_id: str,
        scale_config_override: Any,
        **kwargs: Any,
    ) -> None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        cell_id = Path(out_path).parent.name
        scale_id, method_id, inj_id = _parse_cell_id(cell_id)
        if not method_id:
            method_id = coord_method
        if not inj_id:
            inj_id = injection_id
        data = _minimal_results_json(scale_id, method_id, inj_id)
        Path(out_path).write_text(json.dumps(data), encoding="utf-8")

    import labtrust_gym.studies.coordination_security_pack as pack_mod

    with patch.object(pack_mod, "run_benchmark", side_effect=fake_run_benchmark):
        out_dir = tmp_path / "pack_out"
        run_coordination_security_pack(out_dir=out_dir, repo_root=repo_root, seed_base=42)
        gate_path = out_dir / "pack_gate.md"
        gate_text = gate_path.read_text(encoding="utf-8")
        for inj in PACK_INJECTIONS:
            assert inj in gate_text or inj.replace("-", "_") in gate_text


def test_coordination_security_pack_no_reserved_injection_cells_when_disallow(repo_root: Path, tmp_path: Path) -> None:
    """When pack runs with disallow_reserved_injections (default), no cell has a reserved NoOp injection_id."""
    from labtrust_gym.security.risk_injections import RESERVED_NOOP_INJECTION_IDS

    def fake_run_benchmark(*args: Any, **kwargs: Any) -> None:
        out_path = kwargs.get("out_path")
        if out_path is None:
            return
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cell_id = out_path.parent.name
        scale_id, method_id, inj_id = _parse_cell_id(cell_id)
        method_id = method_id or kwargs.get("coord_method", "kernel_auction_whca_shielded")
        inj_id = inj_id or kwargs.get("injection_id", "none")
        data = _minimal_results_json(scale_id, method_id, inj_id)
        out_path.write_text(json.dumps(data), encoding="utf-8")

    import labtrust_gym.studies.coordination_security_pack as pack_mod

    with patch.object(pack_mod, "run_benchmark", side_effect=fake_run_benchmark):
        out_dir = tmp_path / "pack_out"
        run_coordination_security_pack(out_dir=out_dir, repo_root=repo_root, seed_base=42)
        summary_path = out_dir / "pack_summary.csv"
        assert summary_path.is_file()
        with summary_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        for row in rows:
            inj_id = (row.get("injection_id") or "").strip()
            if inj_id and inj_id != "none":
                assert inj_id not in RESERVED_NOOP_INJECTION_IDS, (
                    f"pack_summary must not contain reserved NoOp injection_id {inj_id!r}"
                )


def test_coordination_security_pack_fixed_matrix_constants() -> None:
    """Pack uses the required fixed matrix (scales, methods, injections)."""
    assert "small_smoke" in PACK_SCALES
    assert "medium_stress_signed_bus" in PACK_SCALES
    assert "kernel_auction_whca_shielded" in PACK_METHODS
    assert "llm_repair_over_kernel_whca" in PACK_METHODS
    assert "llm_local_decider_signed_bus" in PACK_METHODS
    assert "none" in PACK_INJECTIONS
    assert "INJ-ID-SPOOF-001" in PACK_INJECTIONS
    assert "INJ-COMMS-POISON-001" in PACK_INJECTIONS
    assert "INJ-COORD-PROMPT-INJECT-001" in PACK_INJECTIONS
    assert "INJ-CONSENSUS-POISON-001" in PACK_INJECTIONS
    assert "INJ-TIMING-QUEUE-001" in PACK_INJECTIONS


def test_coordination_security_pack_disallows_reserved_injections_when_strict(repo_root: Path, tmp_path: Path) -> None:
    """When disallow_reserved_injections is true, pack fails fast if injection list includes reserved IDs (e.g. inj_device_fail)."""
    import labtrust_gym.studies.coordination_security_pack as pack_mod

    pack_config_strict = {
        "disallow_reserved_injections": True,
        "injection_ids": {"default": ["none", "inj_jailbreak"]},
        "method_ids": {"default": PACK_METHODS},
        "scale_ids": {"default": PACK_SCALES},
    }

    with patch.object(pack_mod, "_load_pack_config", return_value=pack_config_strict):
        with pytest.raises(ValueError) as exc_info:
            run_coordination_security_pack(
                out_dir=tmp_path / "pack_out",
                repo_root=repo_root,
                seed_base=42,
                injections_from="fixed",
            )
        assert "Reserved injection IDs" in str(exc_info.value)
        assert "inj_jailbreak" in str(exc_info.value)


def test_coordination_security_pack_allows_reserved_injections_when_disallow_false(
    repo_root: Path, tmp_path: Path
) -> None:
    """When disallow_reserved_injections is false, pack runs even with reserved IDs in the list (NoOp)."""

    def fake_run_benchmark(
        task_name: str,
        num_episodes: int,
        base_seed: int,
        out_path: Path,
        repo_root: Path,
        coord_method: str,
        injection_id: str,
        scale_config_override: Any,
        **kwargs: Any,
    ) -> None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        cell_id = Path(out_path).parent.name
        scale_id, method_id, inj_id = _parse_cell_id(cell_id)
        if not method_id:
            method_id = coord_method
        if not inj_id:
            inj_id = injection_id
        data = _minimal_results_json(scale_id, method_id, inj_id)
        Path(out_path).write_text(json.dumps(data), encoding="utf-8")

    import labtrust_gym.studies.coordination_security_pack as pack_mod

    pack_config_lenient = {
        "disallow_reserved_injections": False,
        "injection_ids": {"default": ["none", "inj_tool_selection_noise"]},
        "method_ids": {"default": PACK_METHODS},
        "scale_ids": {"default": PACK_SCALES},
    }

    with patch.object(pack_mod, "_load_pack_config", return_value=pack_config_lenient):
        with patch.object(pack_mod, "run_benchmark", side_effect=fake_run_benchmark):
            run_coordination_security_pack(
                out_dir=tmp_path / "pack_out",
                repo_root=repo_root,
                seed_base=42,
                injections_from="fixed",
            )
    assert (tmp_path / "pack_out" / "pack_summary.csv").is_file()


def test_coordination_native_injection_discriminative_resistance(repo_root: Path, tmp_path: Path) -> None:
    """
    For coordination-native injection INJ-CONSENSUS-POISON-001, the designated resistant
    method (llm_local_decider_signed_bus) must show strictly better sec.attack_success_rate
    than at least one other method when metrics are differentiated. Validates that the
    injection is discriminative and metric extraction flows into the attacked summary.
    """
    RESISTANT_METHOD = "llm_local_decider_signed_bus"
    COORD_INJECTION = "INJ-CONSENSUS-POISON-001"

    def fake_run_benchmark(
        task_name: str,
        num_episodes: int,
        base_seed: int,
        out_path: Path,
        repo_root: Path,
        coord_method: str,
        injection_id: str,
        scale_config_override: Any,
        **kwargs: Any,
    ) -> None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        cell_id = Path(out_path).parent.name
        scale_id, method_id, inj_id = _parse_cell_id(cell_id)
        if not method_id:
            method_id = coord_method
        if not inj_id:
            inj_id = injection_id
        attack_rate: float | None = None
        if inj_id == COORD_INJECTION and method_id == RESISTANT_METHOD:
            attack_rate = 0.0
        elif inj_id == COORD_INJECTION:
            attack_rate = 1.0
        data = _minimal_results_json(scale_id, method_id, inj_id)
        if data["episodes"] and data["episodes"][0].get("metrics"):
            data["episodes"][0]["metrics"]["sec"] = {
                "attack_success_rate": attack_rate,
                "detection_latency_steps": 2 if attack_rate else None,
            }
        Path(out_path).write_text(json.dumps(data), encoding="utf-8")

    import labtrust_gym.studies.coordination_security_pack as pack_mod

    with patch.object(pack_mod, "run_benchmark", side_effect=fake_run_benchmark):
        out_dir = tmp_path / "pack_out"
        run_coordination_security_pack(out_dir=out_dir, repo_root=repo_root, seed_base=42)
        summary_path = out_dir / "pack_summary.csv"
        assert summary_path.is_file()
        with summary_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        consensus_rows = [r for r in rows if (r.get("injection_id") or "").strip() == COORD_INJECTION]
        assert len(consensus_rows) >= 2, "need at least 2 methods for INJ-CONSENSUS-POISON-001"
        by_method = {r["method_id"]: r for r in consensus_rows}
        assert RESISTANT_METHOD in by_method
        resistant_rate = by_method[RESISTANT_METHOD].get("sec.attack_success_rate")
        try:
            resistant_val = float(resistant_rate) if resistant_rate not in (None, "") else None
        except (TypeError, ValueError):
            resistant_val = None
        assert resistant_val is not None, "resistant method must have sec.attack_success_rate"
        other_methods = [m for m in by_method if m != RESISTANT_METHOD]
        for other in other_methods:
            other_rate = by_method[other].get("sec.attack_success_rate")
            try:
                other_val = float(other_rate) if other_rate not in (None, "") else None
            except (TypeError, ValueError):
                other_val = None
            if other_val is not None:
                assert resistant_val < other_val, (
                    f"resistant method {RESISTANT_METHOD} must have lower attack_success_rate "
                    f"than {other} for {COORD_INJECTION}"
                )


def test_sec_coord_matrix_001_reduced_matrix(repo_root: Path, tmp_path: Path) -> None:
    """
    SEC-COORD-MATRIX-001: Reduced coordination security matrix run produces pack_summary
    with every method in the list present and at least one PASS verdict (e.g. baseline 'none').
    Uses mocked run_benchmark so CI stays fast; smoke: false in suite.
    """

    def fake_run_benchmark(
        task_name: str,
        num_episodes: int,
        base_seed: int,
        out_path: Path,
        repo_root: Path,
        coord_method: str,
        injection_id: str,
        scale_config_override: Any,
        **kwargs: Any,
    ) -> None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        cell_id = Path(out_path).parent.name
        scale_id, method_id, inj_id = _parse_cell_id(cell_id)
        if not method_id:
            method_id = coord_method
        if not inj_id:
            inj_id = injection_id
        data = _minimal_results_json(scale_id, method_id, inj_id)
        Path(out_path).write_text(json.dumps(data), encoding="utf-8")

    import labtrust_gym.studies.coordination_security_pack as pack_mod

    with patch.object(pack_mod, "run_benchmark", side_effect=fake_run_benchmark):
        out_dir = tmp_path / "pack_out"
        run_coordination_security_pack(
            out_dir=out_dir,
            repo_root=repo_root,
            seed_base=42,
            methods_from="fixed",
            injections_from="critical",
        )
        summary_path = out_dir / "pack_summary.csv"
        assert summary_path.is_file(), "pack_summary.csv must be emitted"
        with summary_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        assert len(rows) >= 1, "at least one row in pack_summary"
        methods_in_summary = {r.get("method_id", "").strip() for r in rows if r.get("method_id")}
        pack_config = _load_pack_config(repo_root)
        expected_methods = _resolve_methods(repo_root, "fixed", pack_config)
        missing = set(expected_methods) - methods_in_summary
        assert not missing, (
            f"SEC-COORD-MATRIX-001: every method in the pack list must appear in pack_summary. Missing: {sorted(missing)}"
        )
        gate_path = out_dir / "pack_gate.md"
        assert gate_path.is_file(), "pack_gate.md must be emitted"
        gate_text = gate_path.read_text(encoding="utf-8")
        pass_count = gate_text.count("| PASS |")
        assert pass_count >= 1, "SEC-COORD-MATRIX-001: at least one cell must PASS (e.g. baseline injection 'none')"
