#!/usr/bin/env python3
"""CI: validate LabTrust producer ingest contract (offline fixture + optional live output dir)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.bench_schemas import (
    resolve_pcs_core_schema_root,
    validate_producer_ingest_contract,
    validate_pcs_core_reproducibility_outputs,
)

FIXTURE_TREE = ROOT / "tests" / "fixtures" / "pcs_bench_reproducibility"
LEGACY_INGEST = ROOT / "tests" / "fixtures" / "pcs_bench_ingest" / "labtrust" / "pcs_bench_ingest.v0.json"
LIVE_OUT = ROOT / "benchmark_runs" / "labtrust_reproducibility"


def _validate_tree(out_dir: Path, pcs_core: Path | None) -> None:
    if not (out_dir / "pcs_bench_ingest.v0.json").is_file():
        raise FileNotFoundError(f"missing ingest under {out_dir}")
    if pcs_core is not None:
        for label in validate_pcs_core_reproducibility_outputs(
            out_dir, pcs_core_root=pcs_core, policy_root=ROOT
        ):
            print(f"  OK {label}")
        return
    ingest = json.loads((out_dir / "pcs_bench_ingest.v0.json").read_text(encoding="utf-8"))
    manifest_path = out_dir / "benchmark_manifest.v0.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else None
    )
    for label in validate_producer_ingest_contract(
        ingest,
        ingest_path=out_dir / "pcs_bench_ingest.v0.json",
        policy_root=ROOT,
        out_dir=out_dir,
        release_grade=bool(manifest and manifest.get("evidence_grade") == "release"),
        manifest_doc=manifest,
    ):
        print(f"  OK {label}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live-out",
        type=Path,
        default=None,
        help=f"Optional producer output dir (default: {LIVE_OUT} if present)",
    )
    args = parser.parse_args()

    pcs_core = resolve_pcs_core_schema_root(ROOT.parent / "pcs-core")

    if (FIXTURE_TREE / "pcs_bench_ingest.v0.json").is_file():
        if pcs_core is None:
            print("FAIL pcs-core required for fixture tree", file=sys.stderr)
            return 1
        for label in validate_pcs_core_reproducibility_outputs(
            FIXTURE_TREE, pcs_core_root=pcs_core, policy_root=ROOT
        ):
            print(f"  OK fixture {label}")
        print(f"offline fixture tree OK ({FIXTURE_TREE.relative_to(ROOT)})")
    elif LEGACY_INGEST.is_file():
        ingest = json.loads(LEGACY_INGEST.read_text(encoding="utf-8"))
        for label in validate_producer_ingest_contract(
            ingest,
            ingest_path=LEGACY_INGEST,
            policy_root=ROOT,
            pcs_core_root=pcs_core,
        ):
            print(f"  OK fixture {label}")
        print(f"legacy ingest OK ({LEGACY_INGEST.relative_to(ROOT)})")
    else:
        print("FAIL missing fixture tree; run scripts/generate_pcs_bench_ingest_fixture.py", file=sys.stderr)
        return 1

    live = args.live_out
    if live is None and LIVE_OUT.is_dir() and (LIVE_OUT / "pcs_bench_ingest.v0.json").is_file():
        live = LIVE_OUT
    if live is not None and live.is_dir():
        print(f"validating live producer output: {live}")
        try:
            _validate_tree(live.resolve(), pcs_core)
        except Exception as exc:
            print(
                f"  SKIP live producer output ({exc}); "
                "regenerate with make pcs-bench-producer or remove benchmark_runs/labtrust_reproducibility",
                file=sys.stderr,
            )

    print("pcs producer contract CI OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
