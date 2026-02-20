# Release checklist

Before tagging a release (e.g. `v0.2.0`), maintainers must ensure the following. This keeps the published artifact and risk register chain valid for forkers.

## Mandatory: E2E artifacts chain

Run the full reproducible artifact chain **and** have it pass. No network; deterministic inputs.

**Unix/macOS (bash):**

```bash
make e2e-artifacts-chain
```

**Or run the script directly:**

```bash
bash scripts/ci_e2e_artifacts_chain.sh
```

**What it does:**

1. **package-release (minimal)** — `labtrust package-release --profile minimal --seed-base 100 --out <work_dir>/release` (writes **ENV/** with deps_freeze.txt, python_runtime.json, git.json for provenance)
2. **export-risk-register** — `labtrust export-risk-register --out <work_dir>/release --runs <work_dir>/release` (writes RISK_REGISTER_BUNDLE.v0.1.json into the release dir for a single release artifact)
3. **build-release-manifest** — `labtrust build-release-manifest --release-dir <work_dir>/release` (writes RELEASE_MANIFEST.v0.1.json with hashes of MANIFEST, evidence bundles, and risk register bundle)
4. **verify-release** — `labtrust verify-release --release-dir <work_dir>/release --strict-fingerprints` (verifies every EvidenceBundle.v0.1, validates risk register bundle if present, verifies RELEASE_MANIFEST hashes; all offline)
5. **Schema and crosswalk** — Validates the risk register bundle against the schema and crosswalk integrity
6. **Bundle references release** — Asserts the bundle has evidence or links

If any step fails, do **not** tag the release. Fix the failure (e.g. verify-bundle hashchain mismatch, policy drift, missing evidence) and re-run.

**CI:** The same chain runs in the [E2E artifacts chain](https://github.com/fraware/LabTrust-Gym/blob/main/.github/workflows/e2e-artifacts-chain.yml) workflow on pull requests, schedule, and workflow_dispatch. You can add it as a required status check for `main` so the chain is green before cutting a release.

**verify-bundle vs verify-release:** `verify-bundle --bundle` accepts a **single** EvidenceBundle.v0.1 directory (one that contains `manifest.json`), e.g. under `receipts/<task>_cond_<n>/EvidenceBundle.v0.1`. The release root (with `MANIFEST.v0.1.json`) is not valid for `--bundle`. To verify a **full** release end-to-end (evidence bundles + risk register + release manifest hashes), use `labtrust verify-release --release-dir <path> --strict-fingerprints`. Use `--strict-fingerprints` so every EvidenceBundle manifest must include coordination_policy_fingerprint, memory_policy_fingerprint, rbac_policy_fingerprint, and tool_registry_fingerprint (default for releases).

## Recommended before release

- `labtrust validate-policy` (and `labtrust validate-policy --partner hsl_like` if using partner overlay)
- `pytest -q` (full test suite green)
- `labtrust determinism-report --task throughput_sla --episodes 3 --seed 42 --out ./det_report` (optional but recommended for reproducibility claims)
- Update `CHANGELOG.md` and version in `pyproject.toml`

## Paper-ready release (make paper)

For a **paper-ready** artifact (paper_v0.1 profile then verify-release), set `OUT` and run:

```bash
make paper OUT=/path/to/out
```

This runs `labtrust package-release --profile paper_v0.1 --seed-base <default> --out $OUT` then `labtrust verify-release --release-dir $OUT --strict-fingerprints`. The paper profile emits ENV/, SECURITY/, baselines, FIGURES/, TABLES/, and coordination outputs; see [Paper provenance](../benchmarks/paper/README.md).

## See also

- [Trust verification](../risk-and-security/trust_verification.md) — What each step in the E2E chain attests and how to run or inspect each artifact.
- [CI gates](ci.md) — What runs on push/PR and optional jobs
- [Forker guide](../getting-started/forkers.md) — How forkers run the pipeline and interpret outputs
- [Troubleshooting](../getting-started/troubleshooting.md) — Common failures (e.g. verify-bundle, policy validation)
