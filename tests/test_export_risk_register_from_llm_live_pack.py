"""
Export risk register from llm_live pack output: assert new transparency links and no crosswalk failures.

Runs the official pack in pipeline_mode=llm_live with allow_network=False (smoke, deterministic),
then export-risk-register on that output, and asserts the bundle contains the new evidence links
(TRANSPARENCY_LOG/llm_live.json, live_evaluation_metadata.json) and has no crosswalk failures.

Gated by LABTRUST_OFFICIAL_PACK_SMOKE=1 or LABTRUST_PAPER_SMOKE=1 (same as other official pack smoke tests).
Network-free and deterministic for CI.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.official_pack import run_official_pack
from labtrust_gym.config import get_repo_root
from labtrust_gym.export.risk_register_bundle import (
    RISK_REGISTER_BUNDLE_FILENAME,
    check_crosswalk_integrity,
    validate_bundle_against_schema,
)


def _skip_unless_official_pack_smoke() -> None:
    if os.environ.get("LABTRUST_OFFICIAL_PACK_SMOKE") != "1" and os.environ.get("LABTRUST_PAPER_SMOKE") != "1":
        pytest.skip("Set LABTRUST_OFFICIAL_PACK_SMOKE=1 or LABTRUST_PAPER_SMOKE=1 to run")


def test_export_risk_register_from_llm_live_pack_artifacts_and_links(
    tmp_path: Path,
) -> None:
    """
    Run official pack (llm_live, no network), then export-risk-register; assert llm_live
    artifacts exist, bundle contains new transparency links, and no crosswalk failures.
    """
    _skip_unless_official_pack_smoke()
    root = get_repo_root()
    pack_dir = tmp_path / "pack_llm_live"
    risk_out_dir = tmp_path / "risk_out"
    risk_out_dir.mkdir(parents=True, exist_ok=True)

    run_official_pack(
        out_dir=pack_dir,
        repo_root=root,
        seed_base=100,
        smoke=True,
        full_security=False,
        pipeline_mode="llm_live",
        allow_network=False,
    )

    assert (pack_dir / "TRANSPARENCY_LOG" / "llm_live.json").exists(), (
        "llm_live pack must produce TRANSPARENCY_LOG/llm_live.json"
    )
    assert (pack_dir / "live_evaluation_metadata.json").exists(), (
        "llm_live pack must produce live_evaluation_metadata.json"
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "labtrust_gym.cli.main",
            "export-risk-register",
            "--out",
            str(risk_out_dir),
            "--runs",
            str(pack_dir.resolve()),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, (
        f"export-risk-register must succeed: stderr={result.stderr!r} stdout={result.stdout!r}"
    )

    bundle_path = risk_out_dir / RISK_REGISTER_BUNDLE_FILENAME
    assert bundle_path.exists(), f"Bundle not written: {bundle_path}"
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    links = bundle.get("links") or []
    link_labels = {lnk.get("label") for lnk in links if lnk.get("label")}

    assert "LLM live transparency log" in link_labels, (
        f"Bundle must contain link to TRANSPARENCY_LOG/llm_live.json; labels={sorted(link_labels)!r}"
    )
    assert "Live evaluation metadata" in link_labels, (
        f"Bundle must contain link to live_evaluation_metadata.json; labels={sorted(link_labels)!r}"
    )

    schema_errors = validate_bundle_against_schema(bundle, root)
    assert schema_errors == [], f"Bundle must pass schema: {schema_errors}"

    crosswalk_errors = check_crosswalk_integrity(bundle)
    assert crosswalk_errors == [], (
        f"Bundle must have no crosswalk failures (evidence/risk/control refs); errors={crosswalk_errors!r}"
    )
