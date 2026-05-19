"""Committed BenchmarkCase.v0 suite (pcs-bench contract)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from labtrust_gym.pcs.benchmark_cases import BENCHMARK_INDEX_NAME, verify_benchmark_cases


def test_committed_benchmark_tree(repo_root: Path) -> None:
    bench = repo_root / "examples" / "pcs_qc_release" / "benchmark"
    assert (bench / BENCHMARK_INDEX_NAME).is_file(), (
        "missing benchmark_index.json; run labtrust generate-benchmark-cases "
        "--out examples/pcs_qc_release/benchmark"
    )
    index = json.loads((bench / BENCHMARK_INDEX_NAME).read_text(encoding="utf-8"))
    assert len(index["cases"]) == 12
    assert index.get("pcs_bench", {}).get("version") == "v0"
    verify_benchmark_cases(bench, policy_root=repo_root)


def test_ci_validate_benchmark_cases_script(repo_root: Path) -> None:
    script = repo_root / "examples/pcs_qc_release/scripts/ci_validate_benchmark_cases.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
