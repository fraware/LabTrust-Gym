#!/usr/bin/env python3
"""Recompute signature_or_digest on workflow_profile.v0.json after editing the body."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from labtrust_gym.pcs.workflow_profile import default_workflow_profile_path, finalize_workflow_profile_digest


def main() -> int:
    path = default_workflow_profile_path(ROOT)
    doc = json.loads(path.read_text(encoding="utf-8"))
    updated = finalize_workflow_profile_digest(doc)
    path.write_text(json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OK updated {path}")
    print(updated["signature_or_digest"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
