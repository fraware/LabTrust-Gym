# Proposal: adopt FailureCaseManifest.v0 in pcs-core

## Summary

LabTrust-Gym ships a reference PCS workflow with a **failure gallery** (negative fixtures for
benchmarks and CI). Each case uses a small JSON sidecar, `failure_case_manifest.json`, defined
in LabTrust as **FailureCaseManifest.v0**.

We propose pcs-core adopt this manifest as a first-class schema so any workflow repo can share
the same gallery contract without copying LabTrust-specific paths.

## Motivation

- **pcs-bench** needs stable `expected_failure_code` and `responsible_component` fields per case.
- CI can validate manifests with `jsonschema` before running expensive verifier checks.
- A second workflow (computation, tool-use) can reuse the same gallery layout as QC release.

## Proposed pcs-core changes

1. Add `schemas/FailureCaseManifest.v0.schema.json` (copy from LabTrust
   `policy/schemas/pcs/FailureCaseManifest.v0.schema.json`).
2. Optional: add `schemas/RegenerationReport.v0.schema.json` for clean-run benchmark reports.
3. Extend `gallery_index.json` (or future `FailureGalleryIndex.v0`) to list
   `failure_case_manifest` paths per case.
4. Document in pcs-core `docs/` beside `WorkflowProfile.v0`.

## Reference implementation

- Schema (LabTrust): `policy/schemas/pcs/FailureCaseManifest.v0.schema.json`
- Human spec: `schemas_or_docs/FailureCaseManifest.v0.md`
- Gallery: `examples/pcs_qc_release/failures/<case_id>/`
- Generator: `labtrust generate-failure-gallery`

## Non-goals

- Defining domain-specific failure codes (workflows own codes; schema only constrains shape).
- Replacing `expected_failure.json` immediately (LabTrust keeps legacy files for one release).

## Compatibility

New schema; no breaking change to existing pcs-core artifact types.
