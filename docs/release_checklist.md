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

1. **package-release (minimal)** — `labtrust package-release --profile minimal --seed-base 100 --out <work_dir>/release`
2. **verify-release** — Verifies every `EvidenceBundle.v0.1` under the release: `labtrust verify-release --release-dir <work_dir>/release`. Note: `verify-bundle` is for a single EvidenceBundle path (e.g. `receipts/.../EvidenceBundle.v0.1`), not the release root.
3. **export-risk-register** — `labtrust export-risk-register --out <work_dir>/risk_out --runs <work_dir>/release`
4. **Schema and crosswalk** — Validates the risk register bundle against the schema and crosswalk integrity
5. **Bundle references release** — Asserts the bundle has evidence or links

If any step fails, do **not** tag the release. Fix the failure (e.g. verify-bundle hashchain mismatch, policy drift, missing evidence) and re-run.

**CI:** The same chain runs in the [E2E artifacts chain](https://github.com/fraware/LabTrust-Gym/blob/main/.github/workflows/e2e-artifacts-chain.yml) workflow on pull requests, schedule, and workflow_dispatch. You can add it as a required status check for `main` so the chain is green before cutting a release.

**verify-bundle vs verify-release:** `verify-bundle --bundle` accepts a **single** EvidenceBundle.v0.1 directory (one that contains `manifest.json`), e.g. under `receipts/<task>_cond_<n>/EvidenceBundle.v0.1`. The release root (with `MANIFEST.v0.1.json`) is not valid for `--bundle`. To verify a **full** release in one go, use `labtrust verify-release --release-dir <path>`; it discovers every `receipts/*/EvidenceBundle.v0.1` and runs the same checks on each. The E2E script uses verify-release so all bundles in the release are verified.

## Recommended before release

- `labtrust validate-policy` (and `labtrust validate-policy --partner hsl_like` if using partner overlay)
- `pytest -q` (full test suite green)
- `labtrust determinism-report --task throughput_sla --episodes 3 --seed 42 --out ./det_report` (optional but recommended for reproducibility claims)
- Update `CHANGELOG.md` and version in `pyproject.toml`

## See also

- [CI gates](ci.md) — What runs on push/PR and optional jobs
- [Forker guide](FORKER_GUIDE.md) — How forkers run the pipeline and interpret outputs
- [Troubleshooting](troubleshooting.md) — Common failures (e.g. verify-bundle, policy validation)
