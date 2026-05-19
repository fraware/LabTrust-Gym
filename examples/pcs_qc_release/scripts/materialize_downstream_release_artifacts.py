#!/usr/bin/env python3
"""Copy and align PF downstream artifacts into examples/pcs_qc_release/release/."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.scientific_memory_import import materialize_downstream_release_artifacts

RELEASE = ROOT / "examples" / "pcs_qc_release" / "release"


def main() -> int:
    if not (RELEASE / "science_claim_bundle.certified.json").is_file():
        raise FileNotFoundError(f"incomplete release tree: {RELEASE}")
    written = materialize_downstream_release_artifacts(RELEASE, policy_root=ROOT)
    for name in written:
        print(f"OK {name}")
    print("downstream release artifacts materialized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
