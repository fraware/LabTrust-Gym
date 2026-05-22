#!/usr/bin/env python3
"""CI: run reproducibility benchmark (full_regeneration with hash_stability fallback)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.benchmark_pcs_bench_ingest import PCS_BENCH_INGEST_NAME
from labtrust_gym.pcs.bench_schemas import resolve_pcs_core_schema_root
from labtrust_gym.pcs.benchmark_report import BENCHMARK_REPORT_NAME
from labtrust_gym.pcs.benchmark_reproducibility import (
    BENCHMARK_MANIFEST_NAME,
    BENCHMARK_RUN_NAME,
    COVERAGE_REPORT_NAME,
    HASH_STABILITY_REPORT_NAME,
    RegenerationUnavailableError,
    benchmark_reproducibility,
)


def _release_canon(pcs_core_root: Path | None) -> Path | None:
    if pcs_core_root is None:
        return None
    canon = pcs_core_root / "examples" / "labtrust-release"
    return canon if (canon / "trace.json").is_file() else None


def main() -> int:
    pcs_core_root = resolve_pcs_core_schema_root(ROOT / "pcs-core")
    release_canon = _release_canon(pcs_core_root)
    release = ROOT / "examples" / "pcs_qc_release" / "release"
    with tempfile.TemporaryDirectory(prefix="labtrust_repro_") as tmp:
        out = Path(tmp)
        doc = benchmark_reproducibility(
            out,
            workflow_key="hospital_lab.qc_release",
            policy_root=ROOT,
            release_dir=release,
            pcs_core=release_canon,
            runs=2,
            seed=42,
            mode="hash_stability",
            include_hash_stability=False,
        )
        try:
            benchmark_reproducibility(
                out / "full_regen_probe",
                workflow_key="hospital_lab.qc_release",
                policy_root=ROOT,
                release_dir=release,
                pcs_core=release_canon,
                runs=1,
                seed=42,
                mode="full_regeneration",
                release_grade=False,
                include_hash_stability=False,
            )
            print("  full_regeneration probe OK")
        except (RegenerationUnavailableError, ValueError) as exc:
            print(f"  full_regeneration skipped ({exc})")
        agg = doc["aggregate"]
        if not agg["command_deterministic"]:
            raise SystemExit(
                "reproducibility benchmark failed aggregate gate: "
                f"artifact_hashes_stable={agg.get('artifact_hashes_stable')} "
                f"canonical_hashes_stable={agg.get('canonical_hashes_stable')} "
                f"release_validation_stable={agg.get('release_validation_stable')}"
            )
        for name in (
            BENCHMARK_RUN_NAME,
            BENCHMARK_MANIFEST_NAME,
            BENCHMARK_REPORT_NAME,
            COVERAGE_REPORT_NAME,
            PCS_BENCH_INGEST_NAME,
        ):
            if not (out / name).is_file():
                raise FileNotFoundError(f"missing reproducibility output: {name}")
        manifest = json.loads((out / BENCHMARK_MANIFEST_NAME).read_text(encoding="utf-8"))
        if manifest.get("evidence_grade") != "developer":
            raise SystemExit("CI hash_stability run must emit developer evidence_grade")
        if pcs_core_root is not None:
            from labtrust_gym.pcs.bench_schemas import validate_pcs_core_reproducibility_outputs

            checks = validate_pcs_core_reproducibility_outputs(
                out, pcs_core_root=pcs_core_root, policy_root=ROOT
            )
            for label in checks:
                print(f"  OK {label}")
    print("reproducibility benchmark CI OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
