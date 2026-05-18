"""CLI smoke for PCS subcommands (subprocess)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytest.importorskip("pcs_core")


def _run(args: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "labtrust_gym.cli.main", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
        check=False,
    )


def test_cli_run_demo_and_validate_pcs(repo_root: Path, tmp_path: Path) -> None:
    run_dir = tmp_path / "qc-release"
    env = {**os.environ, "PCS_DETERMINISTIC": "1"}
    proc = _run(
        ["run-demo", "qc-release", "--deterministic", "--out", str(run_dir), "--validate"],
        cwd=repo_root,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    assert (run_dir / "run_meta.json").is_file()
    meta = json.loads((run_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["released"] is True

    receipt_out = tmp_path / "receipt.json"
    proc = _run(
        ["export-runtime-receipt", "--run", str(run_dir), "--out", str(receipt_out)],
        cwd=repo_root,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    proc = _run(["validate-pcs", "--artifact", str(receipt_out)], cwd=repo_root, env=env)
    assert proc.returncode == 0, proc.stderr


def test_cli_verify_release_fixtures(repo_root: Path) -> None:
    release = repo_root / "examples/pcs_qc_release/release"
    if not (release / "manifest.json").is_file():
        pytest.skip("release fixtures not committed")
    args = ["verify-release-fixtures", "--release-dir", str(release)]
    pcs_core = repo_root.parent / "pcs-core" / "examples" / "labtrust-release"
    if pcs_core.is_dir():
        args.extend(["--pcs-core", str(pcs_core)])
    proc = _run(args, cwd=repo_root)
    assert proc.returncode == 0, proc.stderr


def test_cli_emit_handoff_bundle_to_verifier(release_dir: Path, repo_root: Path, tmp_path: Path) -> None:
    out = tmp_path / "handoff_to_pf.json"
    proc = _run(
        [
            "emit-handoff",
            "--kind",
            "bundle-to-verifier",
            "--bundle",
            str(release_dir / "science_claim_bundle.certified.json"),
            "--out",
            str(out),
            "--release-mode",
        ],
        cwd=repo_root,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.is_file()
