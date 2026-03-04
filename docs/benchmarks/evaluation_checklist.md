# Benchmark evaluation checklist

Use this when launching a new benchmark evaluation or when you have not run the full command set in a long time.

## Baseline status

| Set | Role | Location | Regression |
|-----|------|----------|------------|
| **v0.2** | Canonical (frozen) | `benchmarks/baselines_official/v0.2/` | Yes. CI and local regression compare exact metrics to v0.2. |
| **v0.1** | Legacy | `benchmarks/baselines_official/v0.1/` | No. Not used for regression. |

**Tasks in v0.2:** throughput_sla, stat_insertion, qc_cascade, adversarial_disruption, multi_site_stat, insider_key_misuse, coord_scale, coord_risk (see `benchmarks/baseline_registry.v0.1.yaml`).

**When to regenerate v0.2:** After any change that affects benchmark semantics (engine, policy, task definitions, metrics, or invariants). If baseline regression fails, regenerate with the command below and commit the updated `benchmarks/baselines_official/v0.2/results/` and summaries.

```bash
labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force
```

**Do you need a new baseline version (e.g. v0.3)?** Only if you intentionally change the *contract* (e.g. schema, task set, or comparison rules). For normal code/policy drift, refresh v0.2 with `--force` and commit.

---

## Full command sequence (run-everything)

Run from repo root. Install once: `pip install -e ".[dev,env,docs]"`.

### 1. Fast checks (before benchmarks)

| Step | Command | Purpose |
|------|---------|---------|
| Lint/format | `ruff format --check .` then `ruff check .` | Style and lint |
| Typecheck | `mypy src/` (must pass) | Types |
| No placeholders | `python tools/no_placeholders.py` | No stubs in non-test code |
| Policy validate | `labtrust validate-policy` | Policy YAML/JSON vs schemas |
| Verify bundle | `labtrust verify-bundle --bundle tests/fixtures/ui_fixtures/evidence_bundle/EvidenceBundle.v0.1` | Evidence bundle contract |
| Risk register gate | `labtrust export-risk-register --out ./risk_register_out --runs tests/fixtures/ui_fixtures` then `pytest tests/test_risk_register_contract_gate.py -v` | Risk register contract |
| Pytest fast | `pytest -q -m "not slow"` | Fast test suite (no golden/slow) |

### 2. Golden and determinism

| Step | Command | Purpose |
|------|---------|---------|
| Golden suite | `LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -q` | Scenario correctness vs engine |
| Determinism report | `labtrust determinism-report --task throughput_sla --episodes 3 --seed 42 --out ./det_report` | Determinism check; assert `det_report/determinism_report.json` has `passed: true` |
| Quick-eval | `labtrust quick-eval --seed 42 --out-dir ./labtrust_runs` | 1 episode each: throughput_sla, adversarial_disruption, multi_site_stat |

### 3. Official baselines and regression

| Step | Command | Purpose |
|------|---------|---------|
| Regenerate v0.2 (if needed) | `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force` | Refresh frozen baselines to current code |
| Baseline regression | `LABTRUST_CHECK_BASELINES=1 pytest tests/test_official_baselines_regression.py -v` | Exact metrics vs v0.2; must pass after regeneration |

### 4. Docs and optional E2E

| Step | Command | Purpose |
|------|---------|---------|
| Docs build | `pip install -e ".[docs]" -q && mkdocs build --strict` | MkDocs site |
| E2E artifacts (optional) | `LABTRUST_BATTERY_E2E=1` then run verification script | Full artifact chain (package-release minimal, verify-release, etc.) |

### One-command verification battery

To run steps 1–3 and docs in one go (same as CI):

```bash
bash scripts/run_verification_battery.sh
```

Or: `make verify` (same effect). On Windows, run the equivalent steps manually or use the PowerShell equivalents where available; the script is bash-only.

---

## Benchmark-only quick path

If you only care about benchmarks and baselines:

1. `labtrust generate-official-baselines --out benchmarks/baselines_official/v0.2/ --episodes 3 --seed 123 --force`
2. `LABTRUST_CHECK_BASELINES=1 pytest tests/test_official_baselines_regression.py -v`

Optional: `labtrust quick-eval --seed 42` and `labtrust determinism-report --task throughput_sla --episodes 3 --seed 42 --out ./det_report`.

---

## References

- [CI gates and regression](../operations/ci.md) — What runs in CI and when baselines are required.
- [Security attack suite](../risk-and-security/security_attack_suite.md) — Coordination security pack; [Coordination studies](../coordination/coordination_studies.md) for study matrix.
- [Benchmarks](benchmarks.md) — Task definitions and metrics.
