# LabTrust-Gym make targets
# Optional: use 'make test' and 'make bench-smoke' (bench-smoke requires [env])
# make verify: full verification battery (lint, typecheck, policy, tests, risk-register gate, docs).
# make paper OUT=<dir>: package-release paper_v0.1 then verify-release (requires OUT= output dir).

.PHONY: test golden bench-smoke lint format typecheck policy-validate no-placeholders e2e-artifacts-chain verification-battery verify paper

# Default: run fast test suite (no env optional deps for golden/policy)
test:
	pytest -q --ignore=tests/test_pz_parallel_smoke.py --ignore=tests/test_pz_aec_smoke.py --ignore=tests/test_benchmark_smoke.py

# Full golden suite (requires LABTRUST_RUN_GOLDEN=1 so tests do not skip)
golden:
	LABTRUST_RUN_GOLDEN=1 pytest tests/test_golden_suite.py -q

# Benchmark smoke: 1 episode per task (TaskA, TaskB, TaskC). Requires: pip install -e ".[env]"
bench-smoke:
	labtrust bench-smoke --seed 42

# Or run benchmark smoke via pytest (2 episodes TaskA + determinism)
bench-smoke-pytest:
	pytest tests/test_benchmark_smoke.py -v

lint:
	ruff check .

format:
	ruff format .

typecheck:
	mypy src/

policy-validate:
	labtrust validate-policy

# Fail if placeholder/stub markers or NotImplementedError/501 remain in non-test code/docs/config
no-placeholders:
	python tools/no_placeholders.py

# Full reproducible artifact chain: package-release (minimal) -> verify-bundle -> export-risk-register.
# Requires bash. No network. Deterministic (SEED_BASE=100). Use for CI gate and local one-button proof.
e2e-artifacts-chain:
	bash scripts/ci_e2e_artifacts_chain.sh

# Verification battery: lint, typecheck, no-placeholders, validate-policy, verify-bundle, risk-register gate,
# pytest fast, golden suite, determinism-report, quick-eval, baseline-regression (if baselines exist), docs.
# Requires: pip install -e ".[dev,env,docs]". Set LABTRUST_BATTERY_E2E=1 to also run e2e-artifacts-chain.
verification-battery:
	bash scripts/run_verification_battery.sh

# One-command verify: same as verification-battery (recommended for contributors).
verify: verification-battery

# Paper release: package-release paper_v0.1 then verify-release. Set OUT=<dir> (required).
# Example: make paper OUT=./paper_release
paper:
	@if [ -z "$${OUT}" ]; then echo "OUT is required (e.g. make paper OUT=./paper_release)"; exit 1; fi; \
	labtrust package-release --profile paper_v0.1 --out "$$OUT" --seed-base 100 && \
	labtrust verify-release --release-dir "$$OUT" --strict-fingerprints
