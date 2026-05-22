#!/usr/bin/env python3
"""Apply LabTrust pcs-core schema profiles (RuntimeReceipt, WorkflowProfile) for local/CI parity."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POLICY_PCS = ROOT / "policy" / "schemas" / "pcs"

PROFILES: tuple[tuple[str, str], ...] = (
    ("runtime_receipt.v0.schema.json", "RuntimeReceipt.v0.schema.json"),
    ("WorkflowProfile.v0.schema.json", "WorkflowProfile.v0.schema.json"),
    ("WorkflowProfile.formalization.extension.schema.json", "WorkflowProfile.formalization.extension.schema.json"),
)


def apply_profiles(pcs_core_root: Path) -> None:
    schemas = pcs_core_root / "schemas"
    if not schemas.is_dir():
        raise FileNotFoundError(f"pcs-core schemas dir not found: {schemas}")
    for src_name, dest_name in PROFILES:
        src = POLICY_PCS / src_name
        if not src.is_file():
            raise FileNotFoundError(f"missing LabTrust schema profile: {src}")
        dest = schemas / dest_name
        shutil.copy2(src, dest)
        print(f"OK applied {src_name} -> {dest}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pcs-core",
        type=Path,
        default=ROOT.parent / "pcs-core",
        help="pcs-core repository root (default: ../pcs-core)",
    )
    args = parser.parse_args()
    apply_profiles(args.pcs_core.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
