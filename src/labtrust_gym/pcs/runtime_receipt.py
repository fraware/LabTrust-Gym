"""Build RuntimeReceipt.v0 from a PCS demo run."""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.deterministic import DETERMINISTIC_ENVIRONMENT, use_frozen_environment
from labtrust_gym.pcs.hash import file_digest, pcs_digest
from labtrust_gym.pcs.ids import receipt_id
from labtrust_gym.pcs.policy import policy_hash
from labtrust_gym.pcs.provenance import base_provenance, normalize_timestamp, with_signature
from labtrust_gym.pcs.schema_version import assert_schema_version
from labtrust_gym.pcs.trace import compute_trace_hash
from labtrust_gym.version import __version__

# Receipt status records observation of the run, not workflow success.
RECEIPT_STATUS = "RuntimeObserved"


def _run_outcome(meta: dict[str, Any]) -> str:
    if meta.get("status") == "completed" and meta.get("released"):
        return "passed"
    return "failed"


def build_runtime_receipt(
    run_dir: Path,
    *,
    policy_root: Path | None = None,
) -> dict[str, Any]:
    root = policy_root or get_repo_root()
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    trace = json.loads((run_dir / "trace.json").read_text(encoding="utf-8"))
    trace_path = run_dir / "trace.json"
    events = trace["events"]
    events_hash = pcs_digest({"events": events})
    trace_hash = trace["trace_hash"]
    ended = meta["ended_at"]

    doc: dict[str, Any] = {
        "receipt_id": receipt_id(meta["run_id"]),
        **base_provenance(policy_root=root),
        "run_id": meta["run_id"],
        "status": RECEIPT_STATUS,
        "run_outcome": _run_outcome(meta),
        "final_reason_code": str(meta.get("final_reason_code", "policy_denied")),
        "released": bool(meta.get("released")),
        "environment": (
            dict(DETERMINISTIC_ENVIRONMENT)
            if use_frozen_environment()
            else {
                "platform": platform.platform(),
                "python": sys.version.split()[0],
                "labtrust_version": __version__,
            }
        ),
        "started_at": normalize_timestamp(meta["started_at"]),
        "ended_at": normalize_timestamp(ended),
        "events_hash": events_hash,
        "policy_hash": policy_hash(root),
        "trace_hash": trace_hash,
        "input_hashes": {
            "workflow": pcs_digest({"run_id": meta["run_id"], "scenario": meta.get("scenario_id")}),
        },
        "output_hashes": {
            "trace.json": file_digest(trace_path),
        },
    }
    expected = compute_trace_hash(events, run_id=meta["run_id"], sample_id=meta["sample_id"])
    if trace_hash != expected:
        doc["trace_hash"] = expected
    signed = with_signature(doc)
    assert_schema_version(signed)
    return signed
