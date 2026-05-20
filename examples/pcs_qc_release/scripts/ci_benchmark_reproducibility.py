#!/usr/bin/env python3
"""CI: run reproducibility benchmark (full_regeneration with hash_stability fallback)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.benchmark_reproducibility import benchmark_reproducibility


def main() -> int:
    pcs_core = ROOT / "pcs-core" / "examples" / "labtrust-release"
    if not pcs_core.is_dir():
        pcs_core = None
    release = ROOT / "examples" / "pcs_qc_release" / "release"
    with tempfile.TemporaryDirectory(prefix="labtrust_repro_") as tmp:
        out = Path(tmp)
        try:
            doc = benchmark_reproducibility(
                out,
                workflow_key="hospital_lab.qc_release",
                policy_root=ROOT,
                release_dir=release,
                pcs_core=pcs_core,
                runs=2,
                seed=42,
                mode="full_regeneration",
            )
        except NotImplementedError:
            doc = benchmark_reproducibility(
                out,
                workflow_key="hospital_lab.qc_release",
                policy_root=ROOT,
                release_dir=release,
                pcs_core=pcs_core,
                runs=2,
                seed=42,
                mode="hash_stability",
            )
        if not doc["aggregate"]["command_deterministic"]:
            raise SystemExit("reproducibility benchmark failed aggregate gate")
    print("reproducibility benchmark CI OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
