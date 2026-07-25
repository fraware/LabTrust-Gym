# labtrust-benchmark-v0.2-candidate

Engineering / research **benchmark release candidate** for LabTrust-Gym package
version 0.2.0 (LTG-PR9).

## Status

| Field | Value |
|-------|-------|
| Release id | `labtrust-benchmark-v0.2-candidate` |
| Claim posture | Engineering benchmark only |
| Scientifically reviewed | **false** (UNSIGNED domain-review slots) |
| Clinical / deployment claims | Forbidden — see non-claims freeze |

Manifest: [`release_manifest.json`](release_manifest.json)

## What this candidate binds

* Official baselines pack `benchmarks/baselines_official/v0.2` (policy fingerprint
  recorded in the manifest)
* External integrations pin
  `benchmarks/external_integrations/pinned_release.v1.json`
* VA release pack `benchmarks/verifier_assurance/release_packs/labtrust-va-release-v1`
* Independent review registry (claim flag must remain false until signed)

## Known gaps (honest)

1. **catalog_drift** — explicit uncovered hazard in the coverage matrix.
2. **UNSIGNED independent reviews** — three roles still unsigned; no
   “scientifically reviewed” language.
3. **Golden reviewer fields** — remain `pending-domain-review`; do not mass-approve.

## Non-claims

Reuse the freeze block: [docs/benchmarks/non_claims_freeze.md](../../../docs/benchmarks/non_claims_freeze.md).

## How to cut / verify

Follow [docs/benchmarks/release_runbook.md](../../../docs/benchmarks/release_runbook.md).

CI-friendly smoke:

```bash
pytest -q tests/test_ltg_benchmark_release_dod.py
python scripts/run_ltg_release_dod_smoke.py
```
