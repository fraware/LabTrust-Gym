"""
Evidence bundle verification: manifest integrity, schema validation, hashchain consistency, invariant trace.

verify_bundle(bundle_dir, ...) runs all checks and returns (passed, report, errors).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from labtrust_gym.export.receipts import (
    POLICY_PACK_MANIFEST_FILENAME,
    load_episode_log,
)
from labtrust_gym.policy.loader import (
    PolicyLoadError,
    load_json,
    validate_against_schema,
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_json_file(path: Path) -> Dict[str, Any]:
    """Load JSON file; raise with path on parse error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PolicyLoadError(path, f"invalid JSON: {e}") from e


def _check_manifest_integrity(
    bundle_dir: Path,
    manifest: Dict[str, Any],
    allow_extra_files: bool,
) -> List[str]:
    """Recompute SHA-256 for every file in manifest; check missing/extra. Returns list of errors."""
    errors: List[str] = []
    manifest_paths = {f["path"] for f in manifest.get("files", [])}
    for f in manifest.get("files", []):
        path = f.get("path")
        expected_sha = f.get("sha256")
        if not path or not expected_sha:
            errors.append(f"manifest: file entry missing path or sha256: {f}")
            continue
        full = bundle_dir / path
        if not full.exists():
            errors.append(f"manifest: missing file: {path}")
            continue
        actual = _sha256_file(full)
        if actual != expected_sha:
            errors.append(
                f"manifest: hash mismatch for {path}: expected {expected_sha[:16]}..., got {actual[:16]}..."
            )
    if not allow_extra_files:
        for p in bundle_dir.iterdir():
            if not p.is_file():
                continue
            rel = p.name
            if rel == "manifest.json":
                continue
            if rel not in manifest_paths:
                errors.append(f"manifest: unexpected file (not in manifest): {rel}")
    return errors


def _check_schemas(
    bundle_dir: Path,
    manifest: Dict[str, Any],
    policy_root: Path,
) -> List[str]:
    """Validate manifest and each receipt against JSON schemas. Returns list of errors."""
    errors: List[str] = []
    receipt_schema_path = (
        policy_root / "policy" / "schemas" / "receipt.v0.1.schema.json"
    )
    manifest_schema_path = (
        policy_root / "policy" / "schemas" / "evidence_bundle_manifest.v0.1.schema.json"
    )
    if not receipt_schema_path.exists():
        errors.append(f"schema missing: {receipt_schema_path}")
        return errors
    if not manifest_schema_path.exists():
        errors.append(f"schema missing: {manifest_schema_path}")
        return errors
    receipt_schema = load_json(receipt_schema_path)
    manifest_schema = load_json(manifest_schema_path)
    try:
        validate_against_schema(manifest, manifest_schema, manifest_schema_path)
    except PolicyLoadError as e:
        errors.append(f"manifest schema: {e}")
    for f in manifest.get("files", []):
        path = f.get("path")
        if not path or not path.endswith(".json") or path == "manifest.json":
            continue
        if path == POLICY_PACK_MANIFEST_FILENAME:
            policy_manifest_schema_path = (
                policy_root
                / "policy"
                / "schemas"
                / "policy_pack_manifest.v0.1.schema.json"
            )
            if policy_manifest_schema_path.exists():
                full = bundle_dir / path
                if full.exists():
                    try:
                        data = _load_json_file(full)
                        schema = load_json(policy_manifest_schema_path)
                        validate_against_schema(data, schema, full)
                    except PolicyLoadError as e:
                        errors.append(f"{path}: {e}")
            continue
        if "receipt_" in path and path.endswith(".v0.1.json"):
            full = bundle_dir / path
            if full.exists():
                try:
                    data = _load_json_file(full)
                    validate_against_schema(data, receipt_schema, full)
                except PolicyLoadError as e:
                    errors.append(f"{path}: {e}")
    return errors


def _check_fhir_if_present(bundle_dir: Path) -> List[str]:
    """If fhir_bundle.json exists, validate JSON and minimal structure. Returns list of errors."""
    errors: List[str] = []
    for name in ("fhir_bundle.json", "fhir_bundle_export.v0.1.json"):
        path = bundle_dir / name
        if not path.exists():
            continue
        try:
            data = _load_json_file(path)
        except PolicyLoadError as e:
            errors.append(f"{name}: {e}")
            return errors
        if not isinstance(data, dict):
            errors.append(f"{name}: root must be JSON object")
            return errors
        if data.get("resourceType") != "Bundle":
            errors.append(f"{name}: missing or invalid resourceType (expected Bundle)")
        if "type" not in data:
            errors.append(f"{name}: missing type")
        if "entry" not in data or not isinstance(data.get("entry"), list):
            errors.append(f"{name}: missing or invalid entry array")
        break
    return errors


def _check_hashchain_proof(bundle_dir: Path) -> List[str]:
    """Verify hashchain_proof.json matches last entry of episode_log_subset (head_hash, length, last_event_hash)."""
    errors: List[str] = []
    proof_path = bundle_dir / "hashchain_proof.json"
    log_path = bundle_dir / "episode_log_subset.jsonl"
    if not proof_path.exists():
        errors.append("hashchain_proof.json: missing")
        return errors
    if not log_path.exists():
        errors.append(
            "episode_log_subset.jsonl: missing (required for hashchain check)"
        )
        return errors
    try:
        proof = _load_json_file(proof_path)
    except PolicyLoadError as e:
        errors.append(f"hashchain_proof.json: {e}")
        return errors
    entries = load_episode_log(log_path)
    if not entries:
        if proof.get("length") != 0:
            errors.append(
                f"hashchain_proof: length {proof.get('length')} but episode_log has 0 entries"
            )
        return errors
    last = entries[-1]
    hc = last.get("hashchain") or {}
    expected_head = hc.get("head_hash")
    expected_last = hc.get("last_event_hash")
    expected_len = len(entries)
    if proof.get("head_hash") != expected_head:
        errors.append(
            f"hashchain_proof: head_hash mismatch (proof={proof.get('head_hash', '')[:16]}..., "
            f"last_entry.hashchain.head_hash={str(expected_head)[:16]}...)"
        )
    if proof.get("last_event_hash") != expected_last:
        errors.append("hashchain_proof: last_event_hash mismatch with last entry")
    if proof.get("length") != expected_len:
        errors.append(
            f"hashchain_proof: length {proof.get('length')} != episode_log entries {expected_len}"
        )
    return errors


def _violations_from_log_entry(entry: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize violations from a log entry for comparison."""
    out = []
    for v in entry.get("violations") or []:
        out.append(
            {
                "invariant_id": v.get("invariant_id"),
                "status": v.get("status"),
                "reason_code": v.get("reason_code"),
            }
        )
    return out


def _check_policy_manifest_and_root_hash(
    bundle_dir: Path,
    manifest: Dict[str, Any],
    policy_root: Optional[Path] = None,
) -> List[str]:
    """
    If policy_pack_manifest.v0.1.json is in bundle: when policy_root given, verify
    policy file hashes; recompute root_hash; verify manifest.policy_root_hash and
    each receipt.policy_root_hash match.
    """
    errors: List[str] = []
    manifest_paths = {f.get("path") for f in manifest.get("files", [])}
    if POLICY_PACK_MANIFEST_FILENAME not in manifest_paths:
        return errors
    policy_manifest_path = bundle_dir / POLICY_PACK_MANIFEST_FILENAME
    if not policy_manifest_path.exists():
        errors.append(
            f"{POLICY_PACK_MANIFEST_FILENAME}: listed in manifest but missing"
        )
        return errors
    try:
        policy_manifest = _load_json_file(policy_manifest_path)
    except PolicyLoadError as e:
        errors.append(f"{POLICY_PACK_MANIFEST_FILENAME}: {e}")
        return errors
    expected_root = policy_manifest.get("root_hash")
    if not expected_root:
        errors.append(f"{POLICY_PACK_MANIFEST_FILENAME}: missing root_hash")
        return errors
    # When policy_root given: verify each policy file hash
    if policy_root is not None:
        for f in policy_manifest.get("files", []):
            path = f.get("path")
            expected_sha = f.get("sha256")
            if not path or not expected_sha:
                continue
            full = policy_root / path
            if not full.exists():
                errors.append(f"policy_pack_manifest: policy file not found: {path}")
                continue
            actual = _sha256_file(full)
            if actual != expected_sha:
                errors.append(
                    f"policy_pack_manifest: hash mismatch for {path}: "
                    f"expected {expected_sha[:16]}..., got {actual[:16]}..."
                )
    # Recompute root_hash (same as loader: canonical JSON of {version, partner_id, files})
    payload_dict = {
        "version": policy_manifest.get("version"),
        "partner_id": policy_manifest.get("partner_id"),
        "files": policy_manifest.get("files", []),
    }
    import hashlib

    payload = json.dumps(payload_dict, sort_keys=True, separators=(",", ":"))
    recomputed = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if recomputed != expected_root:
        errors.append(
            f"policy_pack_manifest: root_hash mismatch: "
            f"expected {expected_root[:16]}..., recomputed {recomputed[:16]}..."
        )
    # EvidenceBundle manifest must reference same policy_root_hash
    manifest_policy_hash = manifest.get("policy_root_hash")
    if manifest_policy_hash is None:
        errors.append(
            "manifest: policy_root_hash missing but policy_pack_manifest present"
        )
    elif manifest_policy_hash != expected_root:
        errors.append(
            f"manifest: policy_root_hash does not match policy_pack_manifest "
            f"(manifest={manifest_policy_hash[:16]}..., "
            f"policy_pack={expected_root[:16]}...)"
        )
    # Each receipt that has policy_root_hash must match
    for mf in manifest.get("files", []):
        path = mf.get("path")
        if not path or "receipt_" not in path or not path.endswith(".v0.1.json"):
            continue
        full = bundle_dir / path
        if not full.exists():
            continue
        try:
            receipt = _load_json_file(full)
        except PolicyLoadError:
            continue
        rec_hash = receipt.get("policy_root_hash")
        if rec_hash is None:
            continue
        if rec_hash != expected_root:
            errors.append(
                f"{path}: receipt policy_root_hash does not match "
                f"policy_pack_manifest (receipt={rec_hash[:16]}..., "
                f"expected={expected_root[:16]}...)"
            )
    return errors


def _check_invariant_trace(bundle_dir: Path) -> List[str]:
    """Re-run invariant consistency: violations in episode_log_subset must be superset of invariant_eval_trace."""
    errors: List[str] = []
    log_path = bundle_dir / "episode_log_subset.jsonl"
    trace_path = bundle_dir / "invariant_eval_trace.jsonl"
    if not log_path.exists():
        errors.append(
            "episode_log_subset.jsonl: missing (required for invariant check)"
        )
        return errors
    if not trace_path.exists():
        # Trace can be empty (no violations exported)
        return errors
    entries = load_episode_log(log_path)
    trace_by_step: Dict[int, List[Dict[str, Any]]] = {}
    for line in trace_path.read_text(encoding="utf-8").strip().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"invariant_eval_trace.jsonl: invalid JSON line: {e}")
            return errors
        idx = row.get("step_index")
        if idx is None:
            continue
        trace_by_step.setdefault(idx, []).extend(row.get("violations") or [])
    for step_index, trace_violations in trace_by_step.items():
        if step_index >= len(entries):
            errors.append(
                f"invariant_eval_trace: step_index {step_index} out of range (log has {len(entries)} entries)"
            )
            continue
        log_violations = _violations_from_log_entry(entries[step_index])
        log_ids = {
            (v.get("invariant_id"), v.get("status"), v.get("reason_code"))
            for v in log_violations
        }
        for tv in trace_violations:
            key = (tv.get("invariant_id"), tv.get("status"), tv.get("reason_code"))
            if key not in log_ids:
                errors.append(
                    f"invariant_eval_trace: step {step_index} has violation {tv.get('invariant_id')} "
                    f"not in episode_log (exported trace is not subset of log)"
                )
                break
    return errors


def verify_bundle(
    bundle_dir: Path,
    policy_root: Optional[Path] = None,
    allow_extra_files: bool = False,
) -> Tuple[bool, str, List[str]]:
    """
    Run all verification checks on an EvidenceBundle.v0.1 directory.

    Returns (passed, report_text, errors).
    - Manifest integrity: recompute SHA-256 for every file in manifest; fail on mismatch, missing, or extra (unless allowed).
    - Schema validation: manifest and each receipt against policy schemas; FHIR bundle if present (best-effort structure).
    - Hashchain proof: must match last entry of episode_log_subset (head_hash, length, last_event_hash).
    - Invariant trace: violations in episode_log must be superset of invariant_eval_trace per step.
    """
    bundle_dir = Path(bundle_dir)
    policy_root = policy_root or Path.cwd()
    errors: List[str] = []

    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        return False, "FAIL", ["manifest.json: missing"]

    try:
        manifest = _load_json_file(manifest_path)
    except PolicyLoadError as e:
        return False, "FAIL", [str(e)]

    errors.extend(_check_manifest_integrity(bundle_dir, manifest, allow_extra_files))
    errors.extend(_check_schemas(bundle_dir, manifest, policy_root))
    errors.extend(_check_fhir_if_present(bundle_dir))
    errors.extend(_check_hashchain_proof(bundle_dir))
    errors.extend(_check_invariant_trace(bundle_dir))
    errors.extend(
        _check_policy_manifest_and_root_hash(bundle_dir, manifest, policy_root)
    )

    passed = len(errors) == 0
    count_manifest = len(manifest.get("files", []))
    count_receipts = sum(
        1
        for f in manifest.get("files", [])
        if "receipt_" in str(f.get("path", ""))
        and str(f.get("path", "")).endswith(".v0.1.json")
    )
    report_lines = [
        "VERIFICATION REPORT",
        f"  Bundle: {bundle_dir}",
        f"  Manifest files: {count_manifest}",
        f"  Receipts: {count_receipts}",
        f"  Result: {'PASS' if passed else 'FAIL'}",
    ]
    if errors:
        report_lines.append(f"  First error: {errors[0]}")
        report_lines.append(f"  Total errors: {len(errors)}")
    report = "\n".join(report_lines)
    return passed, report, errors
