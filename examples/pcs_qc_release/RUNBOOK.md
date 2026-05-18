# PCS QC-release end-to-end runbook

## 1. Overview

This runbook walks through the LabTrust-Gym PCS v0.1 QC-release demonstration. LabTrust-Gym simulates a minimal lab workflow (accession, QC, analysis, release), records a hash-chained trace, and exports PCS artifacts (`RuntimeReceipt.v0`, `EvidenceBundle.v0`, `ScienceClaimBundle.v0`). Downstream repos certify the trace, verify and sign the bundle, and import into Scientific Memory.

**Main claim (protocol safety):** A sample may be released only after accession, QC completion, analysis, authorization by a release-capable actor, and satisfaction of the required temporal protocol constraints.

This is a **research/simulation** artifact, not a clinical deployment.

## 2. Repositories required

| Repository | Role |
|------------|------|
| [LabTrust-Gym](https://github.com/fraware/LabTrust-Gym) | Workflow simulation, trace, PCS export |
| [pcs-core](https://github.com/SentinelOps-CI/pcs-core) | Schema validation, canonical hashing |
| [CertifyEdge](https://github.com/fraware/CertifyEdge) | `TraceCertificate.v0` |
| [provability-fabric](https://github.com/SentinelOps-CI/provability-fabric) | Verify and sign bundles |
| [scientific-memory](https://github.com/fraware/scientific-memory) | Import and render signed claims |

## 3. PCS v0.1 clean-checkout chain (release gate)

PCS v0.1 is ready when the full cross-repo chain succeeds. From a **clean LabTrust-Gym clone** at repo root:

```bash
export PCS_DETERMINISTIC=1
bash examples/pcs_qc_release/scripts/run_pcs_v01_clean_chain.sh
```

This runs, in order: LabTrust demos and export → `pcs validate` pending → CertifyEdge emit/verify → LabTrust attach → PF verify/sign/inspect → Scientific Memory import/render. See [docs/pcs_v01_clean_chain.md](../../docs/pcs_v01_clean_chain.md) for the exact manual commands and env overrides.

LabTrust-only segment (CI / no sibling repos):

```bash
bash examples/pcs_qc_release/scripts/run_pcs_v01_clean_chain.sh --labtrust-only
```

## 4. Release candidate mode (pcs-v0.1.0-rc1)

PCS v0.1 release evidence is **not** the same as LabTrust-local CI goldens.

| Directory | Role |
|-----------|------|
| `examples/pcs_qc_release/expected/` | **LabTrust-local** deterministic fixtures for unit tests and `ci_validate_pcs_exports.py`. May use `trace_certificate.mock.v0.json` and frozen `source_commit` values. |
| `examples/pcs_qc_release/release/` | **Canonical RC mirror** of [pcs-core](https://github.com/SentinelOps-CI/pcs-core) `examples/labtrust-release/`. This is the only tree valid as cross-repo release evidence for the trust loop. |

**Rules**

- Only `release/` counts as release evidence for CertifyEdge, Provability Fabric, and Scientific Memory handoff.
- Do **not** manually edit individual files under `release/` (hash linkage and certificate propagation will break).
- Regenerate the **entire** chain atomically (`run_pcs_v01_clean_chain.sh` with `PCS_COPY_TO_RELEASE=1`), or sync from pcs-core after the canonical chain is updated there.

**Sync from canonical pcs-core**

```bash
python -m labtrust_gym.pcs.sync_pcs_core_rc --pcs-core ../pcs-core/examples/labtrust-release
```

**Verify local fixtures match canonical RC (CI gate)**

```bash
python -m labtrust_gym.pcs.sync_pcs_core_rc \
  --verify-only \
  --pcs-core ../pcs-core/examples/labtrust-release
```

Before Provability Fabric signing, confirm `release/handoff_to_pf.json` (HandoffManifest.v0) matches `release/manifest.json` invariants and sign `release/handoff/science_claim_bundle.certified.json`.

```bash
labtrust emit-handoff \
  --kind bundle-to-verifier \
  --bundle examples/pcs_qc_release/release/science_claim_bundle.certified.json \
  --out examples/pcs_qc_release/release/handoff_to_pf.json \
  --release-mode

labtrust emit-release-fragment \
  --release-dir examples/pcs_qc_release/release
```

`handoff_to_pf.json` is **HandoffManifest.v0** (replaces legacy `pf_handoff.json`). `labtrust_release_fragment.json` is the LabTrust-owned portion of **ReleaseManifest.v0** for pcs-core aggregation (not the global cross-repo manifest).

See also `examples/pcs_qc_release/release/README.md`.

## 5. Toolchain requirements

- Python 3.11+
- `pip install -e ".[dev]"` in LabTrust-Gym (use `scripts/setup_pcs_dev` for isolated `.venv-pcs`)
- `pip install -e /path/to/pcs-core/python` for `pcs validate`
- Git (for `source_commit` in non-deterministic runs)
- CertifyEdge, Provability Fabric, and Scientific Memory for the full clean chain (§3)

## 6. Step 1: run valid LabTrust workflow

```bash
labtrust run-demo qc-release
# default output: runs/qc-release/
```

**LabTrust-only smoke** (requires `pcs-core` installed, e.g. `pip install -e ../pcs-core/python`):

```bash
bash examples/pcs_qc_release/scripts/labtrust_only_smoke.sh
```

**Deterministic fixture mode** (golden artifacts / CI only; freezes `source_commit`, environment, and digests):

```bash
labtrust run-demo qc-release --deterministic
# or: PCS_DETERMINISTIC=1 labtrust run-demo qc-release
```

Regenerate committed goldens after schema changes:

```bash
python examples/pcs_qc_release/scripts/generate_golden.py
```

ScienceClaimBundle exports use PCS-core canonical shape: top-level `runtime_receipts` (array) and `certificates` (array). LabTrust does not emit PF legacy `runtime_receipt` (singular).

Handoff bundle for CertifyEdge / Provability Fabric: `labtrust export-pcs-handoff --out handoff/` (see [docs/pcs_handoff.md](../../docs/pcs_handoff.md)).

**In-repo CI scope:** `pytest tests/pcs` plus `python examples/pcs_qc_release/scripts/ci_validate_pcs_exports.py` (deterministic export, `pcs validate`, golden snapshot checks). CertifyEdge, Provability Fabric, and Scientific Memory steps are documented for cross-repo integration but are not executed in `.github/workflows/pcs.yml`.

Verify `runs/qc-release/run_meta.json` has `"status": "completed"`, `"released": true`, `"final_reason_code": "ok"`.

## 7. Step 2: run invalid LabTrust workflows

```bash
labtrust run-demo qc-release-invalid-missing-qc
labtrust run-demo qc-release-invalid-unauthorized
```

Expected: `final_reason_code` is `missing_qc` and `unauthorized_release` respectively; `released` is false.

## 8. Step 3: export trace and runtime receipt

```bash
labtrust export-trace --run runs/qc-release --out trace.json
labtrust export-runtime-receipt --run runs/qc-release --out runtime_receipt.json
labtrust export-pcs --run runs/qc-release --out science_claim_bundle.pending.json
```

Validate with pcs-core when installed:

```bash
pcs validate runtime_receipt.json
pcs validate science_claim_bundle.pending.json
```

`runtime_receipt.json` field `trace_hash` must equal `trace.json` top-level `trace_hash`.

## 9. Step 4: certify trace with CertifyEdge

```bash
certifyedge emit-pcs-certificate \
  --spec templates/hospital_lab/qc_release.stl \
  --trace trace.json \
  --out trace_certificate.json
```

CertifyEdge emits `TraceCertificate.v0` with `trace_hash` aligned to the runtime receipt.

## 10. Step 5: attach TraceCertificate to ScienceClaimBundle

```bash
labtrust attach-certificate \
  --bundle science_claim_bundle.pending.json \
  --certificate trace_certificate.json \
  --out science_claim_bundle.certified.json
```

After attach: `certificates` is non-empty; `claim_artifact.certificate_refs` references the certificate id; `claim_artifact.status` is `CertificateChecked`.

## 11. Step 6: verify and sign with Provability Fabric

```bash
pf verify science-claim science_claim_bundle.certified.json \
  --out verification_result.json
pcs validate verification_result.json
pf sign science-claim science_claim_bundle.certified.json \
  --out signed_science_claim_bundle.json
pcs validate signed_science_claim_bundle.json
pf inspect science-claim signed_science_claim_bundle.json
```

Provability Fabric emits a top-level **`SignedScienceClaimBundle.v0`** object in `signed_science_claim_bundle.json` (artifact class name; not the value of `schema_version`).

**Signed bundle contract (pcs-core v0):**

| Field | Rule |
|-------|------|
| `schema_version` | Always `"v0"` (PCS protocol version), including on `SignedScienceClaimBundle.v0` |
| `science_claim_bundle` | Nested certified `ScienceClaimBundle.v0` from LabTrust |
| Nested bundle shape | `runtime_receipts` (array) and `certificates` (array) only — never PF legacy top-level `runtime_receipt`, `trace_certificate`, or `trace_certificates` on the pending/certified bundle |

LabTrust does not adapt exports to Provability Fabric’s older local schema; PF must consume pcs-core canonical `ScienceClaimBundle.v0`.

Invalid-run `RuntimeReceipt.v0` files use `status: RuntimeObserved` with `run_outcome: failed` and `final_reason_code` set to `missing_qc` or `unauthorized_release` so downstream UIs can explain failures without overloading artifact status.

## 12. Step 7: import into Scientific Memory

```bash
just pcs-import-bundle BUNDLE=signed_science_claim_bundle.json
just pcs-render-claim CLAIM_ID=<claim_id>
```

Use `claim_id` from the signed bundle (`claim-pcs-qc-release-v0.1` in the demo). Scientific Memory imports **`SignedScienceClaimBundle.v0`**, not the pending bundle alone.

## 13. Expected output files

| Path | Artifact |
|------|----------|
| `trace.json` | Hash-chained workflow trace |
| `runtime_receipt.json` | `RuntimeReceipt.v0` |
| `runs/qc-release/pcs/evidence_bundle.json` | `EvidenceBundle.v0` |
| `science_claim_bundle.pending.json` | Pending `ScienceClaimBundle.v0` |
| `science_claim_bundle.certified.json` | Certified bundle |
| `trace_certificate.json` | `TraceCertificate.v0` |
| `signed_science_claim_bundle.json` | `SignedScienceClaimBundle.v0` (PF output) |

Golden references: `examples/pcs_qc_release/expected/` (regenerate with `python examples/pcs_qc_release/scripts/generate_golden.py` from a git checkout).

### Cross-repo handoff artifacts

| Consumer | Files |
|----------|--------|
| CertifyEdge | `valid_trace.json`, `invalid_missing_qc_trace.json`, `invalid_unauthorized_trace.json` (under `expected/`), trace hash rule in [docs/pcs_export.md](../../docs/pcs_export.md) |
| Provability Fabric | `science_claim_bundle.pending.json`, `science_claim_bundle.certified.json`, `runtime_receipt.json`, `trace_certificate.json` |
| Scientific Memory | `signed_science_claim_bundle.json`, `claim_id`, limitations in [docs/pcs_limitations.md](../../docs/pcs_limitations.md) |

## 14. Troubleshooting

- **`pcs validate` fails:** Install pcs-core; ensure digests use `sha256:` prefix and `schema_version` is `v0`.
- **trace_hash mismatch:** Re-export trace and receipt from the same `run_dir`; do not edit events after export.
- **`local_dev: true` on receipts:** Normal when not in a git checkout (`source_commit: local-dev`). Golden fixtures use `--deterministic` / `PCS_DETERMINISTIC=1` instead (frozen `source_commit`, no `local_dev`).
- **attach-certificate fails:** Certificate `trace_hash` must match `runtime_receipt.trace_hash`.
- **Invalid demos pass release:** Check `policy/pcs/roles.yaml`; only `release_manager` is `release_capable`.

## 15. Golden artifacts and release fixtures

See **§4 Release candidate mode** for the `expected/` vs `release/` split. Details below.

### LabTrust-local (`expected/`)

Regenerate (pcs-core + `PCS_DETERMINISTIC=1`):

```bash
python examples/pcs_qc_release/scripts/generate_golden.py
```

Mock certificate file: `trace_certificate.mock.v0.json` (fixed `DETERMINISTIC_CERT_DIGEST` for attach tests only).

### Cross-repo release (`release/`)

Requires CertifyEdge CLI and sibling checkout (or env overrides):

```bash
export PCS_DETERMINISTIC=1
bash examples/pcs_qc_release/scripts/generate_release_candidate.sh
```

Produces `trace.json`, `runtime_receipt.json`, `trace_certificate.json`, pending/certified bundles,
`handoff_to_certifyedge.json`, `handoff_to_pf.json`, `labtrust_release_fragment.json`, and `manifest.json`.

**Phase 2 protocol producer (stable CLI — one command per artifact):**

```bash
labtrust emit-handoff-to-certifyedge \
  --trace examples/pcs_qc_release/release/trace.json \
  --runtime-receipt examples/pcs_qc_release/release/runtime_receipt.json \
  --property-id hospital_lab.qc_release \
  --out examples/pcs_qc_release/release/handoff_to_certifyedge.json

labtrust emit-handoff-to-pf \
  --bundle examples/pcs_qc_release/release/science_claim_bundle.certified.json \
  --out examples/pcs_qc_release/release/handoff_to_pf.json

labtrust emit-release-fragment \
  --release-dir examples/pcs_qc_release/release \
  --out examples/pcs_qc_release/release/labtrust_release_fragment.json

labtrust verify-release-protocol \
  --release-dir examples/pcs_qc_release/release \
  --pcs-core ../pcs-core

labtrust regenerate-release-protocol \
  --pcs-core ../pcs-core \
  --certifyedge-bin certifyedge \
  --out examples/pcs_qc_release/release \
  --summary-out examples/pcs_qc_release/release/protocol_regeneration_summary.json

labtrust check-status-policy \
  --release-dir examples/pcs_qc_release/release

labtrust generate-failure-gallery \
  --workflow hospital_lab.qc_release \
  --out examples/pcs_qc_release/failures

labtrust check-status-policy \
  --release-dir examples/pcs_qc_release/release
```

**WorkflowProfile.v0** (protocol driver): `examples/pcs_qc_release/workflow_profile.v0.json`  
Reference template for new workflows: `docs/reference-workflow-template.md`

After editing the profile body, refresh its digest:

```bash
python examples/pcs_qc_release/scripts/materialize_workflow_profile.py
python examples/pcs_qc_release/scripts/ci_validate_workflow_profile.py
```

**Local CI parity** (matches `.github/workflows/pcs.yml`):

```bash
bash examples/pcs_qc_release/scripts/run_pcs_ci_local.sh
# or: examples/pcs_qc_release/scripts/run_pcs_ci_local.ps1
```

One-shot shell wrapper (same as above, sets `PCS_DETERMINISTIC=1`):

```bash
bash examples/pcs_qc_release/scripts/generate_release_protocol.sh
```

After pcs-core updates, re-align committed `release/` from canonical fixtures:

```bash
python -m labtrust_gym.pcs.sync_pcs_core_rc --pcs-core ../pcs-core/examples/labtrust-release
```

Validate:

```bash
pytest tests/pcs/test_release_fixtures.py -q   # skips if release/ not populated
pytest tests/pcs/test_pcs_release_contract.py -q
pytest tests/pcs/test_release_protocol_producer.py -q
python examples/pcs_qc_release/scripts/ci_validate_release_fixtures.py
python examples/pcs_qc_release/scripts/ci_validate_pcs_exports.py
```

## 16. Limitations

- Simulation only; no real LIS/hospital integration.
- No clinical safety or regulatory claims.
- Trace model is LabTrust-specific; PCS bundles follow pcs-core schemas.
- Certification and signing require external repos and are not bundled in LabTrust-Gym CI by default.

See also [docs/pcs_limitations.md](../../docs/pcs_limitations.md).
