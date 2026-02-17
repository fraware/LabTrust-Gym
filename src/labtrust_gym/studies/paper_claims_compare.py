"""
Compare a paper release directory to a committed snapshot for regression.

API: compare_paper_snapshot(release_dir, snapshot_dir, ...) -> (passed: bool, report: list[str]).
Also: compare_manifests(expected_dict, actual_dict, ...) for in-memory testing.
Numeric comparison uses epsilon; structured JSON by SHA256 or by_status with optional tolerance.
"""

from __future__ import annotations

import json
from pathlib import Path

# Default epsilon for float comparison (e.g. in summary CSV)
DEFAULT_EPSILON = 1e-9


def _manifest_by_key(entries: list[dict]) -> dict[str, dict]:
    """Index manifest entries by 'key' (fallback to 'path' for backward compatibility)."""
    by_key: dict[str, dict] = {}
    for e in entries:
        k = e.get("key") or e.get("path") or ""
        by_key[k] = e
    return by_key


def compare_manifests(
    expected_manifest: dict,
    actual_manifest: dict,
    *,
    optional_keys: set[str] | None = None,
    allow_by_status_delta: bool = False,
    by_status_max_delta: int = 0,
) -> tuple[bool, list[str]]:
    """
    Compare two manifest dicts (each with 'entries' list). No disk I/O.

    Returns (passed, report_lines). Used by compare_paper_snapshot and by tests.
    optional_keys: keys for which sha256/status mismatch is reported but does not fail.
    """
    optional_keys = optional_keys or set()
    report: list[str] = []
    expected_entries = expected_manifest.get("entries") or []
    actual_entries = actual_manifest.get("entries") or []
    expected_by_key = _manifest_by_key(expected_entries)
    actual_by_key = _manifest_by_key(actual_entries)

    all_passed = True
    for key, exp in expected_by_key.items():
        act = actual_by_key.get(key)
        if act is None:
            report.append(f"{key}: missing in actual manifest")
            all_passed = False
            continue

        exp_absent = exp.get("status") == "absent"
        act_absent = act.get("status") == "absent"
        if exp_absent and act_absent:
            continue
        if exp_absent != act_absent:
            exp_str = "absent" if exp_absent else "present"
            act_str = "absent" if act_absent else "present"
            report.append(f"{key}: expected {exp_str}, actual {act_str}")
            all_passed = False
            continue

        # Both present: compare sha256
        exp_sha = exp.get("sha256")
        act_sha = act.get("sha256")
        if exp_sha != act_sha:
            msg = (
                f"{key}: sha256 mismatch (expected {exp_sha[:16]}..., "
                f"actual {act_sha[:16]}...)"
            )
            if key in optional_keys:
                report.append(msg + " (optional, not failing)")
            else:
                report.append(msg)
                all_passed = False

        # Optional: by_status tolerance for risk_bundle
        if (
            key == "risk_bundle"
            and allow_by_status_delta
            and "by_status" in exp
            and "by_status" in act
        ):
            exp_status = exp["by_status"]
            act_status = act["by_status"]
            for k, exp_count in exp_status.items():
                act_count = act_status.get(k, 0)
                if abs(act_count - exp_count) > by_status_max_delta:
                    report.append(
                        f"{key}: by_status[{k}] expected {exp_count}, actual {act_count} "
                        f"(delta > {by_status_max_delta})"
                    )
                    all_passed = False
            for k in act_status:
                if k not in exp_status and act_status[k] > by_status_max_delta:
                    report.append(
                        f"{key}: by_status[{k}] unexpected in actual "
                        f"(count {act_status[k]})"
                    )
                    all_passed = False

    for key in actual_by_key:
        if key not in expected_by_key:
            report.append(
                f"{key}: present in actual but not in expected snapshot "
                "(consider updating snapshot)"
            )
    return all_passed, report


def compare_paper_snapshot(
    release_dir: Path,
    snapshot_dir: Path,
    *,
    epsilon: float = DEFAULT_EPSILON,
    allow_by_status_delta: bool = False,
    by_status_max_delta: int = 0,
    optional_keys: set[str] | None = None,
) -> tuple[bool, list[str]]:
    """
    Compare artifacts from release_dir against the committed snapshot in snapshot_dir.

    Loads expected from snapshot_dir/snapshot_manifest.json, builds actual from
    release_dir in-process, then calls compare_manifests. Returns (passed, report_lines).
    optional_keys: keys for which sha256/status mismatch is reported but does not fail.
    """
    release_dir = Path(release_dir).resolve()
    optional_keys = optional_keys or set()
    snapshot_dir = Path(snapshot_dir).resolve()
    report: list[str] = []

    expected_path = snapshot_dir / "snapshot_manifest.json"
    if not expected_path.exists():
        report.append(f"Missing expected manifest: {expected_path}")
        return False, report

    try:
        expected_data = json.loads(expected_path.read_text(encoding="utf-8"))
    except Exception as e:
        report.append(f"Failed to load expected manifest: {e}")
        return False, report

    from labtrust_gym.studies.paper_claims_snapshot import build_manifest_from_release

    actual_data = build_manifest_from_release(release_dir, snapshot_out=None)
    return compare_manifests(
        expected_data,
        actual_data,
        optional_keys=optional_keys,
        allow_by_status_delta=allow_by_status_delta,
        by_status_max_delta=by_status_max_delta,
    )
