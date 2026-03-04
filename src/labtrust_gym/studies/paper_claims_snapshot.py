"""
Paper claims snapshot: build a deterministic manifest from a paper_v0.1 release.

Used by scripts/extract_paper_claims_snapshot.py (writes to disk) and
paper_claims_compare.compare_paper_snapshot (in-process, no subprocess).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

# Simple artifacts: (key, path_parts under release_dir, path_label for manifest).
_SIMPLE_ARTIFACTS: list[tuple[str, tuple[str, ...], str]] = [
    ("safety_case", ("SAFETY_CASE", "safety_case.json"), "SAFETY_CASE/safety_case.json"),
    ("coverage", ("SECURITY", "coverage.json"), "SECURITY/coverage.json"),
]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _canonical_json(obj: object) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _entry_present(key: str, path_label: str, digest: str, **extra: Any) -> dict:
    out: dict = {"key": key, "path": path_label, "sha256": digest}
    out.update(extra)
    return out


def _entry_absent(key: str, path_label: str) -> dict:
    return {"key": key, "path": path_label, "status": "absent"}


def build_manifest_from_release(
    release_dir: Path,
    snapshot_out: Path | None = None,
) -> dict:
    """
    Build snapshot manifest from a paper_v0.1 release directory.

    When snapshot_out is not None, also writes snapshot_manifest.json and
    optional summary.csv copy into snapshot_out. When None, returns the
    manifest dict only (for in-process comparison).
    """
    release_dir = Path(release_dir).resolve()
    if snapshot_out is not None:
        snapshot_out = Path(snapshot_out).resolve()
        snapshot_out.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict] = []

    # Summary: prefer summary_v0.3.csv, else summary.csv; optional copy to snapshot_out
    tables = release_dir / "TABLES"
    summary_path = tables / "summary_v0.3.csv"
    if not summary_path.exists():
        summary_path = tables / "summary.csv"
    if summary_path.exists():
        digest = _sha256_file(summary_path)
        manifest_entries.append(_entry_present("summary", "TABLES/summary", digest, artifact=summary_path.name))
        if snapshot_out is not None:
            (snapshot_out / "summary.csv").write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        manifest_entries.append(
            _entry_absent("summary", "TABLES/summary") | {"artifact": "summary_v0.3.csv|summary.csv"}
        )

    # SOTA leaderboard: rglob (first match)
    sota_candidates = list(release_dir.rglob("sota_leaderboard.csv"))
    if sota_candidates:
        sota_path = sota_candidates[0]
        rel = str(sota_path.relative_to(release_dir)).replace("\\", "/")
        digest = _sha256_file(sota_path)
        manifest_entries.append(_entry_present("sota_leaderboard", rel, digest))
    else:
        manifest_entries.append(_entry_absent("sota_leaderboard", "summary/sota_leaderboard.csv"))

    # Simple path-based artifacts
    for key, path_parts, path_label in _SIMPLE_ARTIFACTS:
        path = release_dir.joinpath(*path_parts)
        if path.exists():
            manifest_entries.append(_entry_present(key, path_label, _sha256_file(path)))
        else:
            manifest_entries.append(_entry_absent(key, path_label))

    # Risk bundle: root or risk_register_out; optional by_status stats
    risk_bundle = release_dir / "RISK_REGISTER_BUNDLE.v0.1.json"
    if not risk_bundle.exists():
        risk_bundle = release_dir / "risk_register_out" / "RISK_REGISTER_BUNDLE.v0.1.json"
    path_label_rb = "RISK_REGISTER_BUNDLE.v0.1.json"
    if risk_bundle.exists():
        digest = _sha256_file(risk_bundle)
        entry = _entry_present("risk_bundle", path_label_rb, digest)
        try:
            data = json.loads(risk_bundle.read_text(encoding="utf-8"))
            risks = data.get("risk_register", {}).get("risks", [])
            by_status: dict[str, int] = {}
            for r in risks:
                if isinstance(r, dict):
                    ev = r.get("evidence")
                    st = ev.get("status") if isinstance(ev, dict) else None
                    st = st or "unknown"
                    by_status[st] = by_status.get(st, 0) + 1
            entry["by_status"] = by_status
        except Exception:
            pass
        manifest_entries.append(entry)
    else:
        manifest_entries.append(_entry_absent("risk_bundle", path_label_rb))

    manifest = {"version": "v0.1", "entries": manifest_entries}
    if snapshot_out is not None:
        (snapshot_out / "snapshot_manifest.json").write_text(_canonical_json(manifest), encoding="utf-8")
    return manifest
