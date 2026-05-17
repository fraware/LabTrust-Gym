#!/usr/bin/env python3
"""CI entry point: deterministic PCS export + pcs-core validation (see labtrust_gym.pcs.ci_pipeline)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import os

os.environ.setdefault("PCS_DETERMINISTIC", "1")

from labtrust_gym.pcs.ci_pipeline import (  # noqa: E402
    ci_work_parent,
    expected_dir,
    run_deterministic_qc_release_export,
    validate_committed_goldens,
)


def main() -> int:
    work = ci_work_parent()
    work.mkdir(parents=True, exist_ok=True)
    artifacts = run_deterministic_qc_release_export(work)
    print("OK export pipeline", artifacts.run_dir)
    golden_ok = validate_committed_goldens(expected_dir())
    for name in golden_ok:
        print("OK golden", name)
    print("PCS export + pcs-core validation OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
