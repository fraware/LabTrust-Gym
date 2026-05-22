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
    validate_producer_ingest_contract,
)

FIXTURE = ROOT / "tests" / "fixtures" / "pcs_bench_ingest" / "labtrust" / "pcs_bench_ingest.v0.json"


def main() -> int:
    if not FIXTURE.is_file():
        print(f"FAIL missing fixture: {FIXTURE}", file=sys.stderr)
        return 1

    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    pcs_core = resolve_pcs_core_schema_root(ROOT.parent / "pcs-core")
    checks = validate_producer_ingest_contract(
        doc,
        ingest_path=FIXTURE,
        policy_root=ROOT,
        pcs_core_root=pcs_core,
    )
    for label in checks:
        print(f"  OK {label}")
    print(f"pcs-bench ingest fixture OK ({FIXTURE.relative_to(ROOT)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
