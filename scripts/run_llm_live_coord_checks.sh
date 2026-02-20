#!/usr/bin/env bash
# Run all LLM-live tests and trials that use OPENAI_API_KEY. Per-role test skips without ANTHROPIC_API_KEY.
# Usage: LABTRUST_RUN_LLM_LIVE=1 OPENAI_API_KEY=sk-... ./scripts/run_llm_live_coord_checks.sh

set -e
cd "$(dirname "$0")/.."

if [ -z "$OPENAI_API_KEY" ]; then
    echo "Error: OPENAI_API_KEY is not set. Set it to run live tests and trials." >&2
    exit 1
fi

export LABTRUST_RUN_LLM_LIVE=1

# 1) All live tests in test_openai_live.py (coord + agent + two-episode + per-role)
echo ""
echo "=== 1/3 Live pytest: test_openai_live.py -m live (600s per test) ==="
echo ""
python -m pytest tests/test_openai_live.py -m live -v --tb=short --timeout=600

# 2) Prompt-injection live test
echo ""
echo "=== 2/3 Live pytest: prompt-injection openai_live test ==="
echo ""
python -m pytest tests/test_llm_prompt_injection_golden.py::test_openai_live_prompt_injection_schema_valid_and_constrained -v --tb=short --timeout=300

# 3) Trials script: all four methods, 1 episode each
echo ""
echo "=== 3/3 Trials script (all four methods, 1 episode) ==="
echo ""
python scripts/run_llm_coord_trials_openai.py --out-dir labtrust_runs/llm_coord_trials_openai --episodes 1 --trace

echo ""
echo "All LLM-live commands completed successfully."
