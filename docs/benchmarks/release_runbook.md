# Benchmark release runbook (LTG-PR9)

Command sequence to cut an inspectable, independently reproducible
**engineering benchmark** release candidate. Aligns with the scientific
credibility Definition of Done. This runbook does **not** authorize clinical
or “scientifically reviewed” language.

**Non-claims:** [Non-claims freeze](non_claims_freeze.md).

**Candidate metadata:** [`benchmarks/releases/labtrust-benchmark-v0.2-candidate/`](../../benchmarks/releases/labtrust-benchmark-v0.2-candidate/).

## Claim posture (mandatory)

| Claim | Allowed for v0.2-candidate? |
|-------|----------------------------|
| Engineering / research benchmark packaging | Yes, after technical gates below |
| Independently reproducible from artifacts (API/CLI verify path) | Yes, when verify steps pass |
| Scientifically reviewed | **No** while review slots are UNSIGNED and `scientifically_reviewed_claim_allowed` is false |
| Clinically validated / deployment safe | **Never** (non-claims freeze) |

Check claim flag without inventing approvals:

```bash
python -c "from pathlib import Path; from labtrust_gym.policy.independent_review import scientifically_reviewed_claim_allowed as ok; print('claim_allowed=', ok(Path('.')))"
```

Expected today: `claim_allowed= False`.

## 0. Install

From repo root, clean venv recommended:

```bash
pip install -e ".[dev,env,plots]"
# Optional MARL / external-integration smoke:
pip install -e ".[dev,env,plots,marl]"
```

## 1. Conformance and policy (LTG-01 / policy gate)

```bash
labtrust validate-policy
# Prefer API if CLI wiring is broken in a given env:
python -c "from pathlib import Path; from labtrust_gym.policy.validate import validate_policy; e=validate_policy(Path('.')); assert not e, e"
```

API conformance subset (PettingZoo / Gymnasium):

```bash
pytest -q tests/test_pz_api_conformance.py tests/test_gymnasium_check_env.py tests/test_core_env_transitions.py
```

## 2. Default pytest gate

```bash
pytest -q
# Or documented subset (CI-friendly):
pytest -q tests/test_ltg_benchmark_release_dod.py tests/test_independent_review_gate.py tests/test_golden_governance.py tests/test_pcs_release_reconstruction.py tests/test_attack_evidence_contract.py
```

Heavy suites (golden, baselines, MARL) remain opt-in via their existing env flags.

## 3. Quick eval and reproduce

```bash
labtrust quick-eval --seed 42 --out-dir ./labtrust_runs
labtrust reproduce --profile minimal --out ./repro_minimal
```

Full `reproduce` is **not** part of the default DoD smoke (too heavy for CI).
Run it before tagging a public candidate.

## 4. Determinism

```bash
labtrust determinism-report --task throughput_sla --episodes 3 --seed 42 --out ./det_report
# Assert det_report/determinism_report.json has "passed": true
```

## 5. Official pack

CI / smoke:

```bash
labtrust run-official-pack --out ./pack_smoke --smoke
# Coordination optional:
labtrust run-official-pack --out ./pack_smoke --smoke --include-coordination-pack
```

Full (pre-tag):

```bash
labtrust run-official-pack --out ./pack_full --include-coordination-pack
```

Confirm `pack_manifest.json` includes a `reconstruction` block (LTG-PR6).

## 6. Export / verify receipts and release

From an episode log produced by quick-eval or pack:

```bash
labtrust export-receipts --run <episode.jsonl> --out ./receipts_out
labtrust verify-bundle --bundle ./receipts_out/EvidenceBundle.v0.1
```

Minimal package-release chain (see [Trust verification](../risk-and-security/trust_verification.md)):

```bash
labtrust package-release --profile minimal --seed-base 100 --out ./release_out
labtrust export-risk-register --out ./release_out --runs ./release_out
labtrust build-release-manifest --release-dir ./release_out
labtrust verify-release --release-dir ./release_out --strict-fingerprints
```

If `pcs_core` CLI import is broken, prefer API-level checks already covered by
`tests/test_pcs_release_reconstruction.py` and `validate_policy`.

## 7. External integrations pin

```bash
pytest -q tests/test_ltg_external_integrations.py
# Pin path must exist:
# benchmarks/external_integrations/pinned_release.v1.json
```

## 8. Independent review gate status

```bash
labtrust validate-policy   # includes validate_independent_review_gate
pytest -q tests/test_independent_review_gate.py
```

Release may ship as an **engineering benchmark** while slots are
`*.UNSIGNED.json`. Do **not** set `scientifically_reviewed_claim_allowed: true`
or describe the release as scientifically reviewed until three signed approvals
exist ([signed approval gate](../reviews/signed_approval_gate.md)).

## 9. Automated DoD smoke (CI-friendly)

```bash
pytest -q tests/test_ltg_benchmark_release_dod.py
# Or:
python scripts/run_ltg_release_dod_smoke.py
```

Skips heavy reproduce / full pack by default. Set
`LABTRUST_LTG_RELEASE_FULL=1` only when running the full human pre-tag path
documented in this runbook (full steps are still manual CLI above).

## 10. Update candidate notes

1. Refresh digests in
   `benchmarks/releases/labtrust-benchmark-v0.2-candidate/release_manifest.json`
   if baselines / pin / VA pack identity changed.
2. Keep `scientifically_reviewed: false` until the review gate allows otherwise.
3. Cite [non-claims freeze](non_claims_freeze.md) and known gaps (`catalog_drift`,
   UNSIGNED reviews).

## Related

* [Scientific credibility](scientific_credibility.md)
* [Evaluation checklist](evaluation_checklist.md) (broader maintainer battery)
* [Official benchmark pack](official_benchmark_pack.md)
* [External integrations](../agents/external_integrations.md)
* [PyPI releasing](../operations/releasing.md) (package tag; orthogonal to this benchmark candidate)
