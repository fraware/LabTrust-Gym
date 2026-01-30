# LabTrust-Gym make targets
# Optional: use 'make test' and 'make bench-smoke' (bench-smoke requires [env])

.PHONY: test golden bench-smoke lint format typecheck policy-validate

# Default: run fast test suite (no env optional deps for golden/policy)
test:
	pytest -q --ignore=tests/test_pz_parallel_smoke.py --ignore=tests/test_pz_aec_smoke.py --ignore=tests/test_benchmark_smoke.py

# Full test suite including golden suite (no PettingZoo)
golden:
	pytest tests/test_golden_suite.py -q

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
