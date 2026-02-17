"""
Extract a deterministic snapshot from a paper_v0.1 release directory for regression testing.

Input: path to a paper release dir (e.g. from labtrust package-release --profile paper_v0.1 --out <dir>).
Output: snapshot dir (default tests/fixtures/paper_claims_snapshot/v0.1/) containing:
  - snapshot_manifest.json: paths and SHA256 hashes (or "absent") for each tracked artifact.
  - Optional canonical copies or derived stats (see manifest).

No timestamps in output; JSON uses sorted keys for determinism.
"""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> int:
    from labtrust_gym.studies.paper_claims_snapshot import build_manifest_from_release

    parser = argparse.ArgumentParser(
        description="Extract paper claims snapshot from a paper_v0.1 release directory."
    )
    parser.add_argument(
        "release_dir", type=Path,
        help="Path to paper release (package-release --profile paper_v0.1 --out <dir>)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output directory (default: tests/fixtures/paper_claims_snapshot/v0.1)",
    )
    args = parser.parse_args()
    out = args.out
    if out is None:
        repo = Path(__file__).resolve().parent.parent
        out = repo / "tests" / "fixtures" / "paper_claims_snapshot" / "v0.1"
    build_manifest_from_release(args.release_dir, snapshot_out=out)
    print(f"Snapshot written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
