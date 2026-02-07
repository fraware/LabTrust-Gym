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
        "task": "TaskH_COORD_RISK",
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
        run_coordination_security_pack(
            out_dir=out_dir, repo_root=repo_root, seed_base=42
        )
        pack_results = out_dir / "pack_results"
        assert pack_results.is_dir()
        cells = [d for d in pack_results.iterdir() if d.is_dir()]
        expected_cells = len(PACK_SCALES) * len(PACK_METHODS) * len(PACK_INJECTIONS)
        assert len(cells) == expected_cells, f"expected {expected_cells} cell dirs"
        for c in cells:
            assert (c / "results.json").is_file()

        summary_path = out_dir / "pack_summary.csv"
        assert summary_path.is_file()
        with summary_path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames or []
            rows = list(reader)
        assert len(rows) == expected_cells
        for col in ["method_id", "scale_id", "injection_id", "safety.violations_total"]:
            assert col in fieldnames, f"missing column {col}"

        gate_path = out_dir / "pack_gate.md"
        assert gate_path.is_file()
        gate_text = gate_path.read_text(encoding="utf-8")
        assert "PASS" in gate_text
        assert "|" in gate_text
        assert "not_supported" in gate_text or "PASS" in gate_text


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
