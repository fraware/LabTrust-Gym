"""
Evidence bundle verification: manifest integrity, schema validation, hashchain consistency, invariant trace.

verify_bundle(bundle_dir, ...) runs all checks and returns (passed, report, errors).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, cast

from labtrust_gym.config import policy_path
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


def _load_json_file(path: Path) -> dict[str, Any]:
    """Load JSON file; raise with path on parse error."""
    try:
        return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as e:
        raise PolicyLoadError(path, f"invalid JSON: {e}") from e


def _check_manifest_integrity(
    bundle_dir: Path,
    manifest: dict[str, Any],
    allow_extra_files: bool,
) -> list[str]:
    """Recompute SHA-256 for every file in manifest; check missing/extra. Returns list of errors."""
    errors: list[str] = []
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
            errors.append(f"manifest: hash mismatch for {path}: expected {expected_sha[:16]}..., got {actual[:16]}...")
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
    manifest: dict[str, Any],
    policy_root: Path,
) -> list[str]:
    """Validate manifest and each receipt against JSON schemas. Returns list of errors."""
    errors: list[str] = []
    receipt_schema_path = policy_path(policy_root, "schemas", "receipt.v0.1.schema.json")
    manifest_schema_path = policy_path(policy_root, "schemas", "evidence_bundle_manifest.v0.1.schema.json")
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
            policy_manifest_schema_path = policy_path(policy_root, "schemas", "policy_pack_manifest.v0.1.schema.json")
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


def _check_fhir_if_present(bundle_dir: Path) -> list[str]:
    """If fhir_bundle.json exists, validate JSON and minimal structure. Returns list of errors."""
    errors: list[str] = []
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


def _check_hashchain_proof(bundle_dir: Path) -> list[str]:
    """Verify hashchain_proof.json matches last entry of episode_log_subset (head_hash, length, last_event_hash)."""
    errors: list[str] = []
    proof_path = bundle_dir / "hashchain_proof.json"
    log_path = bundle_dir / "episode_log_subset.jsonl"
    if not proof_path.exists():
        errors.append("hashchain_proof.json: missing")
        return errors
    if not log_path.exists():
        errors.append("episode_log_subset.jsonl: missing (required for hashchain check)")
        return errors
    try:
        proof = _load_json_file(proof_path)
    except PolicyLoadError as e:
        errors.append(f"hashchain_proof.json: {e}")
        return errors
    entries = load_episode_log(log_path)
    if not entries:
        if proof.get("length") != 0:
            errors.append(f"hashchain_proof: length {proof.get('length')} but episode_log has 0 entries")
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
        errors.append(f"hashchain_proof: length {proof.get('length')} != episode_log entries {expected_len}")
    return errors


def _violations_from_log_entry(entry: dict[str, Any]) -> list[dict[str, Any]]:
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
    manifest: dict[str, Any],
    policy_root: Path | None = None,
) -> list[str]:
    """
    If policy_pack_manifest.v0.1.json is in bundle: when policy_root given, verify
    policy file hashes; recompute root_hash; verify manifest.policy_root_hash and
    each receipt.policy_root_hash match.
    """
    errors: list[str] = []
    manifest_paths = {f.get("path") for f in manifest.get("files", [])}
    if POLICY_PACK_MANIFEST_FILENAME not in manifest_paths:
        return errors
    policy_manifest_path = bundle_dir / POLICY_PACK_MANIFEST_FILENAME
    if not policy_manifest_path.exists():
        errors.append(f"{POLICY_PACK_MANIFEST_FILENAME}: listed in manifest but missing")
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
        errors.append("manifest: policy_root_hash missing but policy_pack_manifest present")
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


def _check_tool_registry_fingerprint(
    manifest: dict[str, Any],
    policy_root: Path,
) -> list[str]:
    """
    When manifest has tool_registry_fingerprint: load tool registry from policy_root,
    recompute digest, and verify it matches. Returns list of errors.
    """
    errors: list[str] = []
    expected = manifest.get("tool_registry_fingerprint")
    if not expected or not isinstance(expected, str):
        return errors
    try:
        from labtrust_gym.tools.registry import (
            load_tool_registry,
            tool_registry_fingerprint,
        )

        registry = load_tool_registry(policy_root)
        if not registry:
            errors.append(
                "manifest: tool_registry_fingerprint present but policy tool_registry.v0.1.yaml not found or empty"
            )
            return errors
        path_used = policy_path(policy_root, "tool_registry.v0.1.yaml")
        actual = tool_registry_fingerprint(registry)
        if actual != expected:
            errors.append(_fingerprint_mismatch_message(
                "tool_registry_fingerprint", expected, actual, path_used
            ))
    except Exception as e:
        errors.append(f"tool_registry_fingerprint check: {e}")
    return errors


def _check_rbac_policy_fingerprint(
    manifest: dict[str, Any],
    policy_root: Path,
) -> list[str]:
    """
    When manifest has rbac_policy_fingerprint: load RBAC policy from policy_root,
    recompute digest, and verify it matches. Returns list of errors.
    """
    errors: list[str] = []
    expected = manifest.get("rbac_policy_fingerprint")
    if not expected or not isinstance(expected, str):
        return errors
    try:
        from labtrust_gym.auth.authorize import rbac_policy_fingerprint
        from labtrust_gym.engine.rbac import load_rbac_policy

        rbac_path = policy_path(policy_root, "rbac", "rbac_policy.v0.1.yaml")
        rbac_policy = load_rbac_policy(rbac_path)
        if not rbac_policy or not rbac_policy.get("roles"):
            errors.append(
                "manifest: rbac_policy_fingerprint present but policy rbac/rbac_policy.v0.1.yaml not found or empty"
            )
            return errors
        actual = rbac_policy_fingerprint(rbac_policy)
        if actual != expected:
            errors.append(_fingerprint_mismatch_message(
                "rbac_policy_fingerprint", expected, actual, rbac_path
            ))
    except Exception as e:
        errors.append(f"rbac_policy_fingerprint check: {e}")
    return errors


def _fingerprint_mismatch_message(key: str, expected: str, actual: str, path: Path) -> str:
    """Standard message for manifest fingerprint mismatch (expected, actual, resolved path)."""
    return (
        f"manifest: {key} mismatch: expected {expected!r}, actual {actual!r}; "
        f"resolved path for recomputation: {path}"
    )


def _policy_yaml_fingerprint(path: Path) -> str:
    """Compute SHA-256 of canonical JSON of loaded YAML for reproducibility."""
    from labtrust_gym.policy.loader import load_yaml

    data = load_yaml(path)
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _check_coordination_policy_fingerprint(
    manifest: dict[str, Any],
    policy_root: Path,
) -> list[str]:
    """
    When manifest has coordination_policy_fingerprint: load
    policy/coordination_identity_policy.v0.1.yaml, recompute digest, verify.
    """
    errors: list[str] = []
    expected = manifest.get("coordination_policy_fingerprint")
    if not expected or not isinstance(expected, str):
        return errors
    path = policy_path(policy_root, "coordination_identity_policy.v0.1.yaml")
    if not path.exists():
        errors.append(
            "manifest: coordination_policy_fingerprint present but "
            "policy/coordination_identity_policy.v0.1.yaml not found"
        )
        return errors
    try:
        actual = _policy_yaml_fingerprint(path)
        if actual != expected:
            errors.append(_fingerprint_mismatch_message(
                "coordination_policy_fingerprint", expected, actual, path
            ))
    except Exception as e:
        errors.append(f"coordination_policy_fingerprint check: {e}")
    return errors


def _check_prompt_sha256(
    bundle_dir: Path,
    manifest: dict[str, Any],
) -> list[str]:
    """
    When manifest has prompt_sha256: load prompt_fingerprint_inputs.v0.1.json from bundle,
    recompute prompt_sha256 from frozen template + rendered payload, verify match.
    """
    from labtrust_gym.export.receipts import PROMPT_FINGERPRINT_INPUTS_FILENAME

    errors: list[str] = []
    expected = manifest.get("prompt_sha256")
    if not expected or not isinstance(expected, str):
        return errors
    inputs_path = bundle_dir / PROMPT_FINGERPRINT_INPUTS_FILENAME
    if not inputs_path.exists():
        errors.append(
            "manifest: prompt_sha256 present but "
            f"{PROMPT_FINGERPRINT_INPUTS_FILENAME} missing (required to recompute and verify)"
        )
        return errors
    try:
        inputs_data = _load_json_file(inputs_path)
        from labtrust_gym.baselines.coordination.prompt_fingerprint import (
            recompute_prompt_sha256_from_inputs,
        )

        template_id = manifest.get("prompt_template_id") or inputs_data.get("prompt_template_id")
        state_slice = inputs_data.get("state_digest_slice") or {}
        payload_canonical = inputs_data.get("allowed_actions_payload_canonical") or ""
        policy_slice = inputs_data.get("policy_slice")
        if not template_id:
            errors.append("prompt_sha256 check: prompt_template_id missing in manifest and inputs")
            return errors
        actual = recompute_prompt_sha256_from_inputs(
            template_id,
            state_slice,
            payload_canonical,
            policy_slice,
        )
        if actual != expected:
            errors.append(
                f"manifest: prompt_sha256 mismatch: expected {expected[:16]}..., recomputed {actual[:16]}..."
            )
    except Exception as e:
        errors.append(f"prompt_sha256 check: {e}")
    return errors


def _check_memory_policy_fingerprint(
    manifest: dict[str, Any],
    policy_root: Path,
) -> list[str]:
    """
    When manifest has memory_policy_fingerprint: load policy/memory_policy.v0.1.yaml,
    recompute digest, verify.
    """
    errors: list[str] = []
    expected = manifest.get("memory_policy_fingerprint")
    if not expected or not isinstance(expected, str):
        return errors
    path = policy_path(policy_root, "memory_policy.v0.1.yaml")
    if not path.exists():
        errors.append("manifest: memory_policy_fingerprint present but policy/memory_policy.v0.1.yaml not found")
        return errors
    try:
        actual = _policy_yaml_fingerprint(path)
        if actual != expected:
            errors.append(_fingerprint_mismatch_message(
                "memory_policy_fingerprint", expected, actual, path
            ))
    except Exception as e:
        errors.append(f"memory_policy_fingerprint check: {e}")
    return errors


def _check_invariant_trace(bundle_dir: Path) -> list[str]:
    """Re-run invariant consistency: violations in episode_log_subset must be superset of invariant_eval_trace."""
    errors: list[str] = []
    log_path = bundle_dir / "episode_log_subset.jsonl"
    trace_path = bundle_dir / "invariant_eval_trace.jsonl"
    if not log_path.exists():
        errors.append("episode_log_subset.jsonl: missing (required for invariant check)")
        return errors
    if not trace_path.exists():
        # Trace can be empty (no violations exported)
        return errors
    entries = load_episode_log(log_path)
    trace_by_step: dict[int, list[dict[str, Any]]] = {}
    with trace_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
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
        log_ids = {(v.get("invariant_id"), v.get("status"), v.get("reason_code")) for v in log_violations}
        for tv in trace_violations:
            key = (tv.get("invariant_id"), tv.get("status"), tv.get("reason_code"))
            if key not in log_ids:
                errors.append(
                    f"invariant_eval_trace: step {step_index} has violation {tv.get('invariant_id')} "
                    f"not in episode_log (exported trace is not subset of log)"
                )
                break
    return errors


def _check_signatures(
    bundle_dir: Path,
    manifest: dict[str, Any],
    policy_root: Path,
) -> list[str]:
    """Verify manifest and receipt signatures when key registry is available. Returns list of errors."""
    from labtrust_gym.engine.signatures import (
        load_key_registry,
        verify_manifest_signature,
        verify_receipt,
    )

    errors: list[str] = []
    key_registry_path = policy_path(policy_root, "keys", "key_registry.v0.1.yaml")
    if not key_registry_path.exists():
        return errors
    try:
        key_registry = load_key_registry(key_registry_path)
    except Exception:
        return errors
    ok, reason = verify_manifest_signature(manifest, key_registry)
    if not ok and reason:
        errors.append(f"manifest signature: {reason}")
    for f in manifest.get("files", []):
        path = f.get("path")
        if not path or "receipt_" not in str(path) or not str(path).endswith(".v0.1.json"):
            continue
        full = bundle_dir / path
        if not full.exists():
            continue
        try:
            receipt = _load_json_file(full)
        except PolicyLoadError:
            continue
        ok, reason = verify_receipt(receipt, key_registry)
        if not ok and reason:
            errors.append(f"{path} signature: {reason}")
    return errors


REQUIRED_STRICT_FINGERPRINTS = [
    "coordination_policy_fingerprint",
    "memory_policy_fingerprint",
    "rbac_policy_fingerprint",
    "tool_registry_fingerprint",
]


def _check_strict_fingerprints_required(manifest: dict[str, Any]) -> list[str]:
    """When strict_fingerprints is True, require all provenance fingerprints to be present. Returns list of errors."""
    errors: list[str] = []
    for key in REQUIRED_STRICT_FINGERPRINTS:
        val = manifest.get(key)
        if not val or not isinstance(val, str):
            errors.append(f"manifest: strict-fingerprints requires {key!r} (missing or empty)")
    return errors


def verify_bundle(
    bundle_dir: Path,
    policy_root: Path | None = None,
    allow_extra_files: bool = False,
    strict_fingerprints: bool = False,
) -> tuple[bool, str, list[str]]:
    """
    Run all verification checks on an EvidenceBundle.v0.1 directory.

    Returns (passed, report_text, errors).
    - Manifest integrity: recompute SHA-256 for every file in manifest; fail on mismatch, missing, or extra (unless allowed).
    - Schema validation: manifest and each receipt against policy schemas; FHIR bundle if present (best-effort structure).
    - Hashchain proof: must match last entry of episode_log_subset (head_hash, length, last_event_hash).
    - Invariant trace: violations in episode_log must be superset of invariant_eval_trace per step.
    - When strict_fingerprints is True: coordination_policy_fingerprint, memory_policy_fingerprint,
      rbac_policy_fingerprint, and tool_registry_fingerprint must be present in the manifest (for external trust).
    """
    bundle_dir = Path(bundle_dir)
    policy_root = policy_root or Path.cwd()
    errors: list[str] = []

    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        return False, "FAIL", ["manifest.json: missing"]

    try:
        manifest = _load_json_file(manifest_path)
    except PolicyLoadError as e:
        return False, "FAIL", [str(e)]

    if strict_fingerprints:
        errors.extend(_check_strict_fingerprints_required(manifest))

    errors.extend(_check_manifest_integrity(bundle_dir, manifest, allow_extra_files))
    errors.extend(_check_schemas(bundle_dir, manifest, policy_root))
    errors.extend(_check_fhir_if_present(bundle_dir))
    errors.extend(_check_hashchain_proof(bundle_dir))
    errors.extend(_check_invariant_trace(bundle_dir))
    errors.extend(_check_policy_manifest_and_root_hash(bundle_dir, manifest, policy_root))
    errors.extend(_check_tool_registry_fingerprint(manifest, policy_root))
    errors.extend(_check_rbac_policy_fingerprint(manifest, policy_root))
    errors.extend(_check_coordination_policy_fingerprint(manifest, policy_root))
    errors.extend(_check_memory_policy_fingerprint(manifest, policy_root))
    errors.extend(_check_prompt_sha256(bundle_dir, manifest))
    errors.extend(_check_signatures(bundle_dir, manifest, policy_root))

    passed = len(errors) == 0
    count_manifest = len(manifest.get("files", []))
    count_receipts = sum(
        1
        for f in manifest.get("files", [])
        if "receipt_" in str(f.get("path", "")) and str(f.get("path", "")).endswith(".v0.1.json")
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


EVIDENCE_BUNDLE_DIRNAME = "EvidenceBundle.v0.1"
RELEASE_MANIFEST_FILENAME = "RELEASE_MANIFEST.v0.1.json"
RISK_REGISTER_BUNDLE_FILENAME = "RISK_REGISTER_BUNDLE.v0.1.json"


def _sha256_file(path: Path) -> str:
    """SHA-256 hex digest of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_release_manifest(
    release_dir: Path,
    policy_root: Path | None = None,
) -> Path:
    """
    Build RELEASE_MANIFEST.v0.1.json in release_dir with hashes of key artifacts.
    Includes: MANIFEST.v0.1.json, each receipts/*/EvidenceBundle.v0.1 (manifest.json hash),
    RISK_REGISTER_BUNDLE.v0.1.json if present. Call after package-release and optionally
    export-risk-register (into release_dir) to produce a single verifiable release artifact.
    """
    release_dir = Path(release_dir)
    artifacts: list[dict[str, Any]] = []
    manifest_path = release_dir / "MANIFEST.v0.1.json"
    if manifest_path.exists():
        artifacts.append({"path": "MANIFEST.v0.1.json", "sha256": _sha256_file(manifest_path)})
    for bundle_path in discover_evidence_bundles(release_dir):
        rel = bundle_path.relative_to(release_dir)
        manifest_json = bundle_path / "manifest.json"
        if manifest_json.exists():
            path_str = (rel / "manifest.json").as_posix()
            artifacts.append({"path": path_str, "sha256": _sha256_file(manifest_json)})
    risk_bundle_path = release_dir / RISK_REGISTER_BUNDLE_FILENAME
    if risk_bundle_path.exists():
        artifacts.append({"path": RISK_REGISTER_BUNDLE_FILENAME, "sha256": _sha256_file(risk_bundle_path)})
    out = {"version": "0.1", "artifacts": artifacts}
    out_path = release_dir / RELEASE_MANIFEST_FILENAME
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True), encoding="utf-8")
    return out_path


def verify_release_manifest(release_dir: Path) -> list[str]:
    """Verify RELEASE_MANIFEST.v0.1.json hashes match actual files. Returns list of errors."""
    errors: list[str] = []
    manifest_path = release_dir / RELEASE_MANIFEST_FILENAME
    if not manifest_path.exists():
        return errors
    try:
        manifest = _load_json_file(manifest_path)
    except Exception as e:
        return [f"RELEASE_MANIFEST load failed: {e}"]
    for entry in manifest.get("artifacts") or []:
        path_str = entry.get("path")
        expected = entry.get("sha256")
        if not path_str or not expected:
            continue
        full = release_dir / path_str
        if not full.exists():
            errors.append(f"RELEASE_MANIFEST artifact missing: {path_str}")
            continue
        if not full.is_file():
            errors.append(f"RELEASE_MANIFEST artifact not a file: {path_str}")
            continue
        actual = _sha256_file(full)
        if actual != expected:
            errors.append(f"RELEASE_MANIFEST hash mismatch: {path_str} (expected {expected[:16]}..., got {actual[:16]}...)")
    return errors


def discover_evidence_bundles(release_dir: Path) -> list[Path]:
    """
    Discover all EvidenceBundle.v0.1 directories under release_dir/receipts/.

    Returns a sorted list of paths so that verification order is deterministic.
    """
    release_dir = Path(release_dir)
    receipts = release_dir / "receipts"
    if not receipts.is_dir():
        return []
    bundles: list[Path] = []
    for entry in sorted(receipts.iterdir()):
        if not entry.is_dir():
            continue
        candidate = entry / EVIDENCE_BUNDLE_DIRNAME
        if candidate.is_dir() and (candidate / "manifest.json").exists():
            bundles.append(candidate)
    return bundles


def verify_release(
    release_dir: Path,
    policy_root: Path | None = None,
    allow_extra_files: bool = False,
    quiet: bool = False,
    strict_fingerprints: bool = False,
) -> tuple[bool, list[tuple[Path, bool, str, list[str]]], list[str]]:
    """
    Verify release end-to-end: every EvidenceBundle.v0.1, optional risk register bundle,
    and optional RELEASE_MANIFEST.v0.1.json hashes. Offline: no network.

    Returns (all_passed, results, release_errors).
    - results: list of (bundle_path, passed, report, errors) for each EvidenceBundle.
    - release_errors: risk register validation errors and/or RELEASE_MANIFEST hash mismatches.
    When strict_fingerprints is True, each bundle manifest must include all required
    provenance fingerprints (coordination, memory, rbac, tool_registry).
    """
    release_dir = Path(release_dir)
    policy_root = policy_root or Path.cwd()
    release_errors: list[str] = []

    bundles = discover_evidence_bundles(release_dir)
    results: list[tuple[Path, bool, str, list[str]]] = []
    for bundle_path in bundles:
        passed, report, errors = verify_bundle(
            bundle_path,
            policy_root=policy_root,
            allow_extra_files=allow_extra_files,
            strict_fingerprints=strict_fingerprints,
        )
        results.append((bundle_path, passed, report, errors))
        if quiet and not passed:
            break

    risk_bundle_path = release_dir / RISK_REGISTER_BUNDLE_FILENAME
    if risk_bundle_path.exists():
        try:
            from labtrust_gym.export.risk_register_bundle import (
                check_crosswalk_integrity,
                validate_bundle_against_schema,
            )

            bundle_data = json.loads(risk_bundle_path.read_text(encoding="utf-8"))
            release_errors.extend(validate_bundle_against_schema(bundle_data, policy_root))
            release_errors.extend(check_crosswalk_integrity(bundle_data))
        except Exception as e:
            release_errors.append(f"Risk register bundle validation: {e}")

    release_errors.extend(verify_release_manifest(release_dir))

    bundles_passed = all(r[1] for r in results) and len(results) == len(bundles)
    all_passed = bundles_passed and len(release_errors) == 0
    return all_passed, results, release_errors


def verify_bundle_structured(
    bundle_dir: Path,
    policy_root: Path | None = None,
    allow_extra_files: bool = False,
) -> dict[str, Any]:
    """
    Run EvidenceBundle verification and return a structured summary for reviewers.
    Surfaces: manifest hash validity, schema validity, hashchain proof valid,
    invariant trace present/valid, policy fingerprints match (rbac, coordination_identity,
    memory, tool_registry). Used by risk register bundle to show "what was verified".
    """
    bundle_dir = Path(bundle_dir)
    policy_root = policy_root or Path.cwd()
    summary: dict[str, Any] = {
        "manifest_valid": False,
        "schema_valid": False,
        "hashchain_valid": False,
        "invariant_trace_valid": False,
        "policy_fingerprints": {
            "rbac": False,
            "coordination_identity": False,
            "memory": False,
            "tool_registry": False,
        },
        "errors": [],
    }
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        summary["errors"] = ["manifest.json: missing"]
        return summary
    try:
        manifest = _load_json_file(manifest_path)
    except PolicyLoadError as e:
        summary["errors"] = [str(e)]
        return summary

    def _run(check_fn: Any, *args: Any) -> list[str]:
        try:
            return list(check_fn(*args))
        except Exception as e:
            return [f"check failed: {e}"]

    e_manifest = _run(_check_manifest_integrity, bundle_dir, manifest, allow_extra_files)
    e_schema = _run(_check_schemas, bundle_dir, manifest, policy_root)
    e_fhir = _run(_check_fhir_if_present, bundle_dir)
    e_hashchain = _run(_check_hashchain_proof, bundle_dir)
    e_invariant = _run(_check_invariant_trace, bundle_dir)
    e_policy_root = _run(_check_policy_manifest_and_root_hash, bundle_dir, manifest, policy_root)
    e_tool = _run(_check_tool_registry_fingerprint, manifest, policy_root)
    e_rbac = _run(_check_rbac_policy_fingerprint, manifest, policy_root)
    e_coord = _run(_check_coordination_policy_fingerprint, manifest, policy_root)
    e_memory = _run(_check_memory_policy_fingerprint, manifest, policy_root)
    e_prompt = _run(_check_prompt_sha256, bundle_dir, manifest)

    summary["manifest_valid"] = len(e_manifest) == 0
    summary["schema_valid"] = len(e_schema) == 0 and len(e_fhir) == 0
    summary["hashchain_valid"] = len(e_hashchain) == 0
    summary["invariant_trace_valid"] = len(e_invariant) == 0
    summary["policy_fingerprints"]["tool_registry"] = len(e_tool) == 0
    summary["policy_fingerprints"]["rbac"] = len(e_rbac) == 0
    summary["policy_fingerprints"]["coordination_identity"] = len(e_coord) == 0
    summary["policy_fingerprints"]["memory"] = len(e_memory) == 0
    all_errors: list[str] = []
    all_errors.extend(e_manifest)
    all_errors.extend(e_schema)
    all_errors.extend(e_fhir)
    all_errors.extend(e_hashchain)
    all_errors.extend(e_invariant)
    all_errors.extend(e_policy_root)
    all_errors.extend(e_tool)
    all_errors.extend(e_rbac)
    all_errors.extend(e_coord)
    all_errors.extend(e_memory)
    all_errors.extend(e_prompt)
    summary["errors"] = all_errors
    return summary
