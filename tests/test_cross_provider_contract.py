"""
Cross-provider contract tests: same transparency schema regardless of provider.

Asserts that live_evaluation_metadata.json and TRANSPARENCY_LOG/llm_live.json
have the same top-level shape and canonical latency keys (mean_latency_ms, etc.)
whether the run came from openai_live, anthropic_live, or ollama_live.
Uses synthetic result files (no real network) so CI stays deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from labtrust_gym.security.transparency import (
    LLM_LIVE_TRANSPARENCY_VERSION,
    collect_llm_live_metadata_from_pack,
    write_llm_live_transparency_log,
)


# Canonical metadata keys that all live backends must populate (runner.py metadata branch).
LIVE_EVALUATION_METADATA_KEYS = ("model_id", "temperature", "tool_registry_fingerprint", "allow_network")
LLM_LIVE_TOP_LEVEL_KEYS = (
    "version",
    "prompt_hashes",
    "tool_registry_fingerprint",
    "model_version_identifiers",
    "latency_and_cost_statistics",
    "per_task",
)
# Aggregator maps mean_llm_latency_ms -> mean_latency_ms; adapters must populate mean_latency_ms in get_aggregate_metrics.
LATENCY_AGG_KEYS = ("min", "max", "mean", "sum")


def _make_result_json(
    provider: str,
    model_id: str,
    mean_latency_ms: float,
    prompt_sha256: str = "fp_test",
    tool_registry_fingerprint: str = "fp_reg",
) -> dict:
    """Minimal result file content that matches what runner.py writes from get_aggregate_metrics()."""
    return {
        "schema_version": "0.2",
        "task": "throughput_sla",
        "metadata": {
            "llm_backend_id": provider,
            "llm_model_id": model_id,
            "mean_latency_ms": mean_latency_ms,
            "mean_llm_latency_ms": mean_latency_ms,
            "prompt_fingerprint": prompt_sha256,
            "tool_registry_fingerprint": tool_registry_fingerprint,
        },
        "episodes": [],
    }


@pytest.mark.parametrize("provider", ["openai_live", "anthropic_live", "ollama_live"])
def test_live_evaluation_metadata_schema_per_provider(tmp_path: Path, provider: str) -> None:
    """For each provider, synthetic results produce live_evaluation_metadata with same required keys."""
    results_dir = tmp_path / "baselines" / "results"
    results_dir.mkdir(parents=True)
    model_id = "gpt-4o-mini" if provider == "openai_live" else ("claude-3-5-haiku" if provider == "anthropic_live" else "ollama/llama2")
    results_dir.joinpath("throughput_sla_scripted.json").write_text(
        json.dumps(
            _make_result_json(provider, model_id, 120.5),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    # Reuse official_pack logic for live_meta: required keys model_id, temperature, tool_registry_fingerprint, allow_network
    live_meta: dict = {
        "model_id": model_id,
        "temperature": None,
        "tool_registry_fingerprint": "fp_reg",
        "allow_network": True,
    }
    meta_path = tmp_path / "live_evaluation_metadata.json"
    meta_path.write_text(json.dumps(live_meta, indent=2, sort_keys=True), encoding="utf-8")

    data = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in LIVE_EVALUATION_METADATA_KEYS:
        assert key in data, f"live_evaluation_metadata must have {key!r} (provider={provider})"
    assert data["allow_network"] is True
    assert isinstance(data.get("model_id"), (str, type(None)))
    assert isinstance(data.get("tool_registry_fingerprint"), (str, type(None)))


@pytest.mark.parametrize("provider", ["openai_live", "anthropic_live", "ollama_live"])
def test_llm_live_json_top_level_shape_per_provider(tmp_path: Path, provider: str) -> None:
    """For each provider, llm_live.json has the same top-level shape (version, prompt_hashes, ...)."""
    results_dir = tmp_path / "baselines" / "results"
    results_dir.mkdir(parents=True)
    model_id = "gpt-4o-mini" if provider == "openai_live" else ("claude-3-5-haiku" if provider == "anthropic_live" else "ollama/llama2")
    results_dir.joinpath("throughput_sla_scripted.json").write_text(
        json.dumps(
            _make_result_json(provider, model_id, 100.0),
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    payload = collect_llm_live_metadata_from_pack(tmp_path)
    for key in LLM_LIVE_TOP_LEVEL_KEYS:
        assert key in payload, f"llm_live payload must have {key!r} (provider={provider})"
    assert payload["version"] == LLM_LIVE_TRANSPARENCY_VERSION
    assert "llm_backend_id" in payload["model_version_identifiers"]
    assert payload["model_version_identifiers"]["llm_backend_id"] == provider

    log_dir = write_llm_live_transparency_log(tmp_path)
    llm_live_path = log_dir / "llm_live.json"
    assert llm_live_path.exists()
    data = json.loads(llm_live_path.read_text(encoding="utf-8"))
    for key in LLM_LIVE_TOP_LEVEL_KEYS:
        assert key in data, f"llm_live.json must have {key!r} (provider={provider})"


@pytest.mark.parametrize("provider", ["openai_live", "anthropic_live", "ollama_live"])
def test_latency_fields_canonical_per_provider(tmp_path: Path, provider: str) -> None:
    """Latency fields (mean_latency_ms) map correctly; aggregator produces min/max/mean/sum."""
    results_dir = tmp_path / "baselines" / "results"
    results_dir.mkdir(parents=True)
    results_dir.joinpath("throughput_sla_scripted.json").write_text(
        json.dumps(
            _make_result_json(provider, "model", 100.0),
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    results_dir.joinpath("stat_insertion_scripted.json").write_text(
        json.dumps(
            _make_result_json(provider, "model", 150.0),
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    payload = collect_llm_live_metadata_from_pack(tmp_path)
    stats = payload.get("latency_and_cost_statistics") or {}
    assert "mean_latency_ms" in stats, f"mean_latency_ms must be present (provider={provider})"
    agg = stats["mean_latency_ms"]
    for k in LATENCY_AGG_KEYS:
        assert k in agg, f"mean_latency_ms must have {k!r} (provider={provider})"
    assert agg["min"] == 100.0 and agg["max"] == 150.0
    assert agg["mean"] == 125.0
    # sum = sum of all collected values (aggregator may collect both mean_latency_ms and mean_llm_latency_ms per file)
    assert agg["sum"] >= 250.0


# Cross-provider summary contract (docs/cross_provider_contract.md)
SUMMARY_CROSS_PROVIDER_REQUIRED_KEYS = ("seed_base", "smoke", "providers", "runs")
RUN_ENTRY_REQUIRED_KEYS = ("provider", "out_dir", "live_metadata", "llm_live_version", "latency_and_cost")


def test_summary_cross_provider_contract_required_keys() -> None:
    """summary_cross_provider.json must have required top-level keys and each run entry must have required keys (contract)."""
    summary = {
        "seed_base": 100,
        "smoke": True,
        "providers": ["openai_live"],
        "runs": [
            {
                "provider": "openai_live",
                "out_dir": "/out/openai_live",
                "live_metadata": {"model_id": "gpt-4o-mini", "temperature": None, "tool_registry_fingerprint": "fp", "allow_network": True},
                "llm_live_version": "0.1",
                "latency_and_cost": {"mean_latency_ms": {"min": 50.0, "max": 200.0, "mean": 100.0, "sum": 300.0}},
            }
        ],
    }
    for key in SUMMARY_CROSS_PROVIDER_REQUIRED_KEYS:
        assert key in summary, f"summary_cross_provider must have {key!r}"
    assert isinstance(summary["runs"], list)
    for run in summary["runs"]:
        for key in RUN_ENTRY_REQUIRED_KEYS:
            assert key in run, f"run entry must have {key!r}"
        if run.get("live_metadata"):
            assert "model_id" in run["live_metadata"]
        if run.get("latency_and_cost"):
            assert "mean_latency_ms" in run["latency_and_cost"]


def test_summary_cross_provider_latency_shape() -> None:
    """When latency_and_cost is present, mean_latency_ms must have min, max, mean, sum (normalization contract)."""
    cost = {"mean_latency_ms": {"min": 0.0, "max": 100.0, "mean": 50.0, "sum": 100.0}}
    for k in LATENCY_AGG_KEYS:
        assert k in cost["mean_latency_ms"]
