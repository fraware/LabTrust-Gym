#!/usr/bin/env python3
"""
Re-run LLM attacker baseline and fail if any previously blocked payload is now accepted.

Usage:
  python scripts/check_llm_attacker_regression.py --baseline <path> [--policy-root <path>] [--seed N]

Reads llm_attacker_baseline.json (from a prior run with --llm-attacker), re-runs each
entry that had outcome "blocked" through the same shield/decoder path, and exits with
code 1 if any payload that was blocked is now accepted (regression).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _load_dotenv_if_available() -> None:
    """Load .env from cwd or LABTRUST_DOTENV_PATH so OPENAI_API_KEY etc. are set (when python-dotenv is installed)."""
    try:
        from dotenv import load_dotenv

        path = os.environ.get("LABTRUST_DOTENV_PATH", "").strip() or ".env"
        load_dotenv(path)
    except ImportError:
        pass


def main() -> int:
    _load_dotenv_if_available()
    parser = argparse.ArgumentParser(
        description="Re-run LLM attacker baseline; fail if previously blocked payload is now accepted."
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        required=True,
        help="Path to llm_attacker_baseline.json (e.g. <out_dir>/SECURITY/llm_attacker_baseline.json).",
    )
    parser.add_argument(
        "--policy-root",
        type=Path,
        default=None,
        help="Policy root (repo root). Default: parent of baseline or cwd.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed for deterministic agent (default 42).",
    )
    args = parser.parse_args()
    policy_root = args.policy_root or args.baseline.resolve().parent.parent
    if not args.baseline.exists():
        print(f"Baseline file not found: {args.baseline}", file=sys.stderr)
        return 1
    from labtrust_gym.benchmarks.security_runner import run_llm_attacker_baseline_regression

    passed, failures = run_llm_attacker_baseline_regression(
        args.baseline,
        policy_root,
        seed=args.seed,
    )
    if not passed and failures:
        for msg in failures:
            print(msg, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
