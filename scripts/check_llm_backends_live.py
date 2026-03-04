#!/usr/bin/env python3
"""
Minimal LLM backend check: call openai_live and/or anthropic_live with one propose_action
and print success/error, tokens, and any exception message.

Use to verify API keys and network before running the full pack. Example:
  python scripts/check_llm_backends_live.py
  python scripts/check_llm_backends_live.py --backends openai_live
  LABTRUST_ALLOW_NETWORK=1 python scripts/check_llm_backends_live.py --backends openai_live,anthropic_live
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Ensure labtrust_gym is importable (repo root or installed).
if __name__ == "__main__":
    _repo = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    if _repo not in sys.path:
        sys.path.insert(0, _repo)

# Load .env from repo root so OPENAI_API_KEY / ANTHROPIC_API_KEY are available.
_repo_root = Path(__file__).resolve().parent.parent
_env_file = _repo_root / ".env"
if _env_file.is_file():
    try:
        from dotenv import load_dotenv

        load_dotenv(_env_file)
    except ImportError:
        # No python-dotenv; parse .env manually (KEY="value" or KEY=value).
        for line in _env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v

# Must allow network and set pipeline mode for live backends.
os.environ.setdefault("LABTRUST_ALLOW_NETWORK", "1")


def _set_llm_live_state() -> None:
    """Set pipeline config so check_network_allowed() passes in backends."""
    from labtrust_gym.pipeline import set_pipeline_config

    set_pipeline_config(pipeline_mode="llm_live", allow_network=True)


logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
LOG = logging.getLogger("check_llm_backends_live")


def _minimal_context() -> dict:
    """Minimal propose_action context (same shape the runner passes)."""
    return {
        "role_id": "ops_0",
        "partner_id": "",
        "policy_fingerprint": None,
        "now_ts_s": 0,
        "timing_mode": "explicit",
        "state_summary": {},
        "allowed_actions": ["NOOP", "TICK", "QUEUE_RUN", "START_RUN", "RELEASE_RESULT"],
        "active_tokens": [],
        "recent_violations": [],
        "enforcement_state": None,
    }


def _check_openai_live() -> dict:
    """One propose_action call with OpenAILiveBackend; return result + metrics + last_metrics."""
    _set_llm_live_state()
    from labtrust_gym.baselines.llm.backends.openai_live import OpenAILiveBackend

    backend = OpenAILiveBackend()
    ctx = _minimal_context()
    try:
        out = backend.propose_action(ctx)
    except Exception as e:
        return {
            "backend_id": "openai_live",
            "success": False,
            "exception": str(e),
            "aggregate_metrics": backend.get_aggregate_metrics(),
            "last_metrics": backend.last_metrics,
        }
    agg = backend.get_aggregate_metrics()
    return {
        "backend_id": "openai_live",
        "success": agg.get("error_count", 0) == 0,
        "action_type": out.get("action_type"),
        "aggregate_metrics": agg,
        "last_metrics": backend.last_metrics,
    }


def _check_anthropic_live() -> dict:
    """One propose_action call with AnthropicLiveBackend; return result + metrics + last_metrics."""
    _set_llm_live_state()
    from labtrust_gym.baselines.llm.backends.anthropic_live import AnthropicLiveBackend

    backend = AnthropicLiveBackend()
    ctx = _minimal_context()
    try:
        out = backend.propose_action(ctx)
    except Exception as e:
        return {
            "backend_id": "anthropic_live",
            "success": False,
            "exception": str(e),
            "aggregate_metrics": backend.get_aggregate_metrics(),
            "last_metrics": backend.last_metrics,
        }
    agg = backend.get_aggregate_metrics()
    return {
        "backend_id": "anthropic_live",
        "success": agg.get("error_count", 0) == 0,
        "action_type": out.get("action_type"),
        "aggregate_metrics": agg,
        "last_metrics": backend.last_metrics,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Check live LLM backends with one propose_action call.")
    ap.add_argument(
        "--backends",
        default="openai_live,anthropic_live",
        help="Comma-separated: openai_live, anthropic_live (default: both)",
    )
    ap.add_argument("--json", action="store_true", help="Output machine-readable JSON only.")
    args = ap.parse_args()
    backends = [b.strip() for b in args.backends.split(",") if b.strip()]

    results = []
    for name in backends:
        if name == "openai_live":
            results.append(_check_openai_live())
        elif name == "anthropic_live":
            results.append(_check_anthropic_live())
        else:
            LOG.warning("Unknown backend %s, skipping", name)

    if args.json:
        print(json.dumps(results, indent=2))
        return 0 if all(r.get("success") for r in results) else 1

    exit_code = 0
    for r in results:
        bid = r.get("backend_id", "?")
        success = r.get("success", False)
        print(f"\n--- {bid} ---")
        print(f"  success: {success}")
        if r.get("exception"):
            print(f"  exception: {r['exception']}")
            exit_code = 1
        agg = r.get("aggregate_metrics") or {}
        print(
            f"  total_calls: {agg.get('total_calls')}, error_count: {agg.get('error_count')}, error_rate: {agg.get('error_rate')}"
        )
        print(f"  total_tokens: {agg.get('total_tokens')}, mean_latency_ms: {agg.get('mean_latency_ms')}")
        last = r.get("last_metrics") or {}
        if last.get("error_message"):
            print(f"  last_metrics.error_message: {last['error_message']}")
            exit_code = 1
        if last.get("error_code"):
            print(f"  last_metrics.error_code: {last['error_code']}")
            if last.get("error_code") != "OK":
                exit_code = 1
        if last.get("error_code") == "LLM_PROVIDER_ERROR" and not last.get("error_message"):
            print(
                "  (LLM_PROVIDER_ERROR with no error_message usually means OPENAI_API_KEY / ANTHROPIC_API_KEY not set or empty)"
            )
    print()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
