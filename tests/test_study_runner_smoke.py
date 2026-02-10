"""
Study runner smoke test: tiny study (2 conditions, 2 episodes), run twice,
assert deterministic output (identical result_hashes and manifest structure).

Requires: pip install -e ".[env]"
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.studies.study_runner import run_study


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _minimal_spec_yaml() -> str:
    """Minimal spec: 2 conditions (trust_skeleton on/off), 1 episode each for fast smoke."""
    return """
task: throughput_sla
episodes: 1
seed_base: 100
timing_mode: explicit
ablations:
  trust_skeleton: [on, off]
  rbac: [coarse]
agent_config: scripted_runner
"""


def test_study_runner_smoke_deterministic_hashes() -> None:
    """Run same study twice in temp dirs; result_hashes and condition layout must be identical."""
    root = _repo_root()
    spec_content = _minimal_spec_yaml()

    with tempfile.TemporaryDirectory() as tmp1:
        with tempfile.TemporaryDirectory() as tmp2:
            spec_path1 = Path(tmp1) / "spec.yaml"
            spec_path2 = Path(tmp2) / "spec.yaml"
            spec_path1.write_text(spec_content, encoding="utf-8")
            spec_path2.write_text(spec_content, encoding="utf-8")
            out1 = Path(tmp1) / "out"
            out2 = Path(tmp2) / "out"

            manifest1 = run_study(spec_path1, out1, repo_root=root)
            manifest2 = run_study(spec_path2, out2, repo_root=root)

            assert manifest1["num_conditions"] == 2
            assert manifest2["num_conditions"] == 2
            assert manifest1["condition_ids"] == ["cond_0", "cond_1"]
            assert manifest2["condition_ids"] == ["cond_0", "cond_1"]
            assert "condition_labels" in manifest1
            assert len(manifest1["condition_labels"]) == 2
            assert len(manifest2["condition_labels"]) == 2

            assert manifest1["result_hashes"] == manifest2["result_hashes"], (
                "Same spec + same code + same seeds => identical per-condition result hashes"
            )
            assert len(manifest1["result_hashes"]) == 2
            assert len(manifest2["result_hashes"]) == 2

            assert (out1 / "manifest.json").exists()
            assert (out1 / "conditions.jsonl").exists()
            assert (out1 / "results" / "cond_0" / "results.json").exists()
            assert (out1 / "results" / "cond_1" / "results.json").exists()
            assert (out1 / "logs" / "cond_0" / "episodes.jsonl").exists()
            assert (out1 / "logs" / "cond_1" / "episodes.jsonl").exists()


def test_study_runner_output_structure() -> None:
    """Assert artifact dir contains manifest.json, conditions.jsonl, results/<id>/, logs/<id>/."""
    root = _repo_root()
    with tempfile.TemporaryDirectory() as tmp:
        spec_path = Path(tmp) / "spec.yaml"
        spec_path.write_text(_minimal_spec_yaml(), encoding="utf-8")
        out_dir = Path(tmp) / "study_out"
        run_study(spec_path, out_dir, repo_root=root)

        manifest_path = out_dir / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "condition_ids" in manifest
        assert "result_hashes" in manifest
        assert "task" in manifest
        assert "episodes" in manifest
        assert "seed_base" in manifest
        assert "num_conditions" in manifest
        assert manifest.get("python_version")

        conditions_path = out_dir / "conditions.jsonl"
        assert conditions_path.exists()
        lines = conditions_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2
        for line in lines:
            rec = json.loads(line)
            assert "condition_id" in rec
            assert "condition_label" in rec
            assert "condition" in rec
            assert "condition_seed" in rec

        for cid in ["cond_0", "cond_1"]:
            assert (out_dir / "results" / cid / "results.json").exists()
            assert (out_dir / "logs" / cid / "episodes.jsonl").exists()
