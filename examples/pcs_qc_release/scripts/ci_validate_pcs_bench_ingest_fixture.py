#!/usr/bin/env python3
"""CI: validate committed offline PcsBenchIngest.v0 fixture (pcs-bench producer gate)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.bench_schemas import (
    resolve_pcs_core_schema_root,
    validate_pcs_core_reproducibility_outputs,
)

FIXTURE_TREE = ROOT / "tests" / "fixtures" / "pcs_bench_reproducibility"
LEGACY_INGEST = ROOT / "tests" / "fixtures" / "pcs_bench_ingest" / "labtrust" / "pcs_bench_ingest.v0.json"


def main() -> int:
    tree = FIXTURE_TREE if (FIXTURE_TREE / "pcs_bench_ingest.v0.json").is_file() else None
    if tree is None and not LEGACY_INGEST.is_file():
        print(
            "FAIL missing fixture: run python scripts/generate_pcs_bench_ingest_fixture.py",
            file=sys.stderr,
        )
        return 1

    pcs_core = resolve_pcs_core_schema_root(ROOT.parent / "pcs-core")
    if tree is not None:
        if pcs_core is None:
            print("FAIL pcs-core required for fixture tree validation", file=sys.stderr)
            return 1
        checks = validate_pcs_core_reproducibility_outputs(
            tree, pcs_core_root=pcs_core, policy_root=ROOT
        )
        for label in checks:
            print(f"  OK {label}")
        print(f"pcs-bench reproducibility fixture OK ({tree.relative_to(ROOT)})")
    elif LEGACY_INGEST.is_file() and pcs_core is not None:
        from labtrust_gym.pcs.bench_schemas import validate_producer_ingest_contract

        doc = json.loads(LEGACY_INGEST.read_text(encoding="utf-8"))
        checks = validate_producer_ingest_contract(
            doc,
            ingest_path=LEGACY_INGEST,
            policy_root=ROOT,
            pcs_core_root=pcs_core,
        )
        for label in checks:
            print(f"  OK {label}")
        print(f"legacy ingest fixture OK ({LEGACY_INGEST.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
