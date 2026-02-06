"""
Pipeline mode: deterministic vs llm_offline vs llm_live and network gating.

- Unit: deterministic run cannot call network even if OPENAI_API_KEY exists.
- Unit: results.json and index.json contain pipeline_mode.
- Integration: llm_live without allow-network fails with clear error.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")


def test_deterministic_run_cannot_call_network_even_with_openai_key() -> None:
    """With pipeline_mode=deterministic, live backend must not perform HTTP even if OPENAI_API_KEY is set."""
    from labtrust_gym.baselines.llm.backends.openai_live import OpenAILiveBackend
    from labtrust_gym.pipeline import set_pipeline_config

    set_pipeline_config(
        pipeline_mode="deterministic", allow_network=False, llm_backend_id=None
    )
    with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test-key"}, clear=False):
        backend = OpenAILiveBackend()
    with pytest.raises(RuntimeError) as exc_info:
        backend.generate([{"role": "user", "content": "test"}])
    assert "Network is not allowed" in str(exc_info.value)
    assert (
        "deterministic" in str(exc_info.value).lower()
        or "pipeline" in str(exc_info.value).lower()
    )


def test_deterministic_run_results_contain_pipeline_mode(tmp_path: Path) -> None:
    """run_benchmark with default (deterministic) writes pipeline_mode in results.json."""
    from labtrust_gym.benchmarks.runner import run_benchmark
    from labtrust_gym.config import get_repo_root

    out = tmp_path / "results.json"
    run_benchmark(
        task_name="TaskA",
        num_episodes=1,
        base_seed=99,
        out_path=out,
        repo_root=get_repo_root(),
        pipeline_mode="deterministic",
        allow_network=False,
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data.get("pipeline_mode") == "deterministic"


def test_results_json_includes_pipeline_fields_for_reviewer(tmp_path: Path) -> None:
    """results.json includes pipeline_mode, llm_backend_id, llm_model_id, allow_network so reviewer knows which pipeline ran."""
    from labtrust_gym.benchmarks.runner import run_benchmark
    from labtrust_gym.config import get_repo_root

    out = tmp_path / "results.json"
    run_benchmark(
        task_name="TaskA",
        num_episodes=1,
        base_seed=99,
        out_path=out,
        repo_root=get_repo_root(),
        pipeline_mode="deterministic",
        allow_network=False,
    )
    data = json.loads(out.read_text(encoding="utf-8"))
    assert "pipeline_mode" in data
    assert data["pipeline_mode"] == "deterministic"
    assert "llm_backend_id" in data
    assert data["llm_backend_id"] == "none"
    assert "allow_network" in data
    assert data["allow_network"] is False
    assert "llm_model_id" in data
    assert data["llm_model_id"] is None


def test_llm_live_without_allow_network_fails_with_clear_message(
    tmp_path: Path,
) -> None:
    """run_benchmark with llm_backend=openai_live and allow_network=False raises RuntimeError with clear message."""
    from labtrust_gym.benchmarks.runner import run_benchmark
    from labtrust_gym.config import get_repo_root

    with patch.dict(os.environ, {}, clear=False):
        if "LABTRUST_ALLOW_NETWORK" in os.environ:
            del os.environ["LABTRUST_ALLOW_NETWORK"]
        with pytest.raises(RuntimeError) as exc_info:
            run_benchmark(
                task_name="TaskA",
                num_episodes=1,
                base_seed=42,
                out_path=tmp_path / "out_llm_live_fail.json",
                repo_root=get_repo_root(),
                llm_backend="openai_live",
                pipeline_mode="llm_live",
                allow_network=False,
            )
    msg = str(exc_info.value)
    assert "allow-network" in msg or "LABTRUST_ALLOW_NETWORK" in msg
    assert "Live LLM" in msg or "network" in msg.lower()


def test_ollama_live_respects_network_gate() -> None:
    """OllamaLiveBackend.generate raises RuntimeError when network is not allowed."""
    from labtrust_gym.baselines.llm.backends.ollama_live import OllamaLiveBackend
    from labtrust_gym.pipeline import set_pipeline_config

    set_pipeline_config(
        pipeline_mode="llm_offline", allow_network=False, llm_backend_id=None
    )
    backend = OllamaLiveBackend()
    with pytest.raises(RuntimeError) as exc_info:
        backend.generate([{"role": "user", "content": "test"}])
    assert "Network is not allowed" in str(exc_info.value)


def test_ui_export_index_includes_pipeline_fields_when_present(tmp_path: Path) -> None:
    """UI export index.json contains pipeline_mode, llm_backend_id, llm_model_id, allow_network when run has them."""
    import zipfile

    from labtrust_gym.config import get_repo_root
    from labtrust_gym.export.ui_export import export_ui_bundle

    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "metadata.json").write_text(
        json.dumps(
            {
                "pipeline_mode": "deterministic",
                "llm_backend_id": "none",
                "llm_model_id": None,
                "allow_network": False,
                "seed_base": 100,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (run_dir / "_repr").mkdir()
    (run_dir / "_baselines").mkdir()
    (run_dir / "receipts").mkdir()
    out_zip = tmp_path / "ui_bundle.zip"
    export_ui_bundle(run_dir, out_zip, repo_root=get_repo_root())

    with zipfile.ZipFile(out_zip, "r") as zf:
        index_data = json.loads(zf.read("index.json"))
    assert index_data.get("pipeline_mode") == "deterministic"
    assert index_data.get("llm_backend_id") == "none"
    assert index_data.get("allow_network") is False
    assert "llm_model_id" in index_data


def test_pipeline_mode_deterministic_rejects_live_backend(tmp_path: Path) -> None:
    """Explicit pipeline_mode=deterministic with llm_backend=openai_live raises ValueError."""
    from labtrust_gym.benchmarks.runner import run_benchmark
    from labtrust_gym.config import get_repo_root

    with pytest.raises(ValueError) as exc_info:
        run_benchmark(
            task_name="TaskA",
            num_episodes=1,
            base_seed=42,
            out_path=tmp_path / "out_reject.json",
            repo_root=get_repo_root(),
            llm_backend="openai_live",
            pipeline_mode="deterministic",
            allow_network=False,
        )
    assert "deterministic" in str(exc_info.value).lower()
    assert "live" in str(exc_info.value).lower()


def test_pipeline_mode_llm_offline_rejects_live_backend(tmp_path: Path) -> None:
    """pipeline_mode=llm_offline with llm_backend=openai_live raises ValueError."""
    from labtrust_gym.benchmarks.runner import run_benchmark
    from labtrust_gym.config import get_repo_root

    with pytest.raises(ValueError) as exc_info:
        run_benchmark(
            task_name="TaskA",
            num_episodes=1,
            base_seed=42,
            out_path=tmp_path / "out_offline_reject.json",
            repo_root=get_repo_root(),
            llm_backend="openai_live",
            pipeline_mode="llm_offline",
            allow_network=False,
        )
    assert "llm_offline" in str(exc_info.value).lower()
    assert (
        "deterministic" in str(exc_info.value).lower()
        or "live" in str(exc_info.value).lower()
    )
