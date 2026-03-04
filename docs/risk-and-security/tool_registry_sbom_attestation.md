# Tool registry: SBOM and attestation (optional extensions)

This document describes optional extensions to the tool registry for state-of-the-art coverage of **R-TOOL-003 (Unverified tool risk)** and **R-TOOL-006 (Tool vulnerability exploitation)**: SBOM (Software Bill of Materials), attestation, and publisher verification. The current suite evidences R-TOOL-003 via **SEC-TOOL-UNVERIFIED-001** (unregistered tool denied); these extensions are roadmap improvements.

## Current controls

- **Registry and allowlist:** Only tools listed in `policy/tool_registry.v0.1.yaml` (or equivalent) may be invoked; unregistered `tool_id` is blocked with `TOOL_NOT_IN_REGISTRY`.
- **Pre-action validation:** `check_tool_allowed` and `validate_tool_args` run before execution; evidence in `tests.test_tool_sandbox::test_unregistered_tool_denied`.
- **Fingerprinting:** `tool_registry_fingerprint()` provides a content hash for reproducibility and EvidenceBundle.

## Optional schema extensions (v0.2)

The following fields are **optional** and can be added to each tool entry when policy requires stronger provenance:

| Field | Type | Description |
|-------|------|-------------|
| `sbom_ref` | string | Path or URI to a CycloneDX/SPDX SBOM for the tool artifact. Validator may resolve and check for known CVEs. |
| `attestation_ref` | string | Path or URI to an in-toto or sigstore attestation. Validator may verify signature and predicate. |
| `publisher_verified` | boolean | If true, policy requires that the publisher identity was verified (e.g. via OCI image signing or release signature). |
| `cve_scan_ref` | string | Optional path/URI to CVE scan results; runner or export may fail closed when scan is stale or high severity. |

When a policy flag (e.g. `require_sbom: true` in tool_registry or gate config) is set, the loader or runner should:

1. For each tool with `sbom_ref` or `attestation_ref`, validate that the ref exists and (if implemented) that the attestation is valid.
2. If `require_sbom` is true and a tool has no `sbom_ref`, treat as configuration error or exclude from allowed set (fail closed).
3. When `cve_scan_ref` is present, optional CVE check can run in CI or export; critical/high CVEs can block release or emit a waiver requirement.

## Validation hook

`validate_registry_sbom(registry, policy_root, require_sbom=False)` in `src/labtrust_gym/tools/registry.py`:

- Returns a list of errors (e.g. missing sbom_ref when require_sbom is True; local path refs checked when policy_root is set).
- Is called from `labtrust validate-policy` when `--strict-tool-provenance` is set, or when the loaded registry has `require_sbom: true`. In both cases, every tool must have `sbom_ref` or a validation error is emitted.

Attestation signature verification and CVE scan parsing are not implemented; only presence of refs and (for local paths) file existence are checked. R-TOOL-003 remains evidenced by SEC-TOOL-UNVERIFIED-001 (unregistered tool denied); when require_sbom is true and validation is wired, coverage extends to "SBOM present and validated."

## Data-class coverage (R-TOOL-006)

Tool output data-class enforcement (PII/PHI vs Operational) is evidenced by **SEC-TOOL-DATACLASS-001** (`tests.test_tool_sandbox::test_data_class_violation_phi_not_allowed`): output containing PHI when the tool policy allows only Operational is blocked with `TOOL_DATA_CLASS_VIOLATION`. SEC-TOOL-001 (full test_tool_sandbox) also exercises egress and byte/record caps.

## References

- [Risk register](risk_register.md) — R-TOOL-003, R-TOOL-006
- [Security attack suite](security_attack_suite.md) — SEC-TOOL-UNVERIFIED-001, SEC-TOOL-001/002/003, SEC-TOOL-DATACLASS-001
- `src/labtrust_gym/tools/registry.py` — load_tool_registry, validate_registry_hashes, check_tool_allowed
- `policy/tool_registry.v0.1.yaml` — current tool registry schema
