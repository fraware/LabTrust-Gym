"""LabTrust segment of PCS v0.1 clean-checkout chain (no CertifyEdge/PF/SM required)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from labtrust_gym.config import get_repo_root

pytest.importorskip("pcs_core")

ROOT = get_repo_root()
SCRIPT = ROOT / "examples" / "pcs_qc_release" / "scripts" / "run_pcs_v01_clean_chain.sh"
VERIFY = ROOT / "examples" / "pcs_qc_release" / "scripts" / "verify_pcs_v01_chain.py"


@pytest.fixture
def chain_work(tmp_path: Path) -> Path:
    return tmp_path / "chain_work"


def test_pcs_v01_clean_chain_labtrust_segment(chain_work: Path) -> None:
    """Deterministic LabTrust demos + export + pcs validate pending (chain steps 1-2)."""
    if not SCRIPT.is_file():
        pytest.skip("run_pcs_v01_clean_chain.sh not present")
    env = {
        **os.environ,
        "PCS_DETERMINISTIC": "1",
        "PCS_CHAIN_WORK": str(chain_work),
        "RUN_DIR": str(chain_work / "runs" / "qc-release"),
    }
    python = sys.executable
    if (ROOT / ".venv-pcs" / "Scripts" / "python.exe").is_file():
        python = str(ROOT / ".venv-pcs" / "Scripts" / "python.exe")

    # Run LabTrust segment via Python (portable on Windows without bash).
    sys.path.insert(0, str(ROOT / "src"))
    os.environ["PCS_DETERMINISTIC"] = "1"
    from labtrust_gym.pcs.demo import run_demo
    from labtrust_gym.pcs.deterministic import deterministic_mode
    from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt, export_trace

    run_dir = chain_work / "runs" / "qc-release"
    with deterministic_mode():
        run_demo("qc-release", out_dir=run_dir, policy_root=ROOT, deterministic=True)
        run_demo("qc-release-invalid-missing-qc", out_dir=chain_work / "missing", policy_root=ROOT, deterministic=True)
        run_demo(
            "qc-release-invalid-unauthorized",
            out_dir=chain_work / "unauthorized",
            policy_root=ROOT,
            deterministic=True,
        )
        export_trace(run_dir, chain_work / "trace.json")
        export_runtime_receipt(run_dir, chain_work / "runtime_receipt.json", policy_root=ROOT)
        export_pcs_bundle(run_dir, chain_work / "science_claim_bundle.pending.json", policy_root=ROOT)

    subprocess.run(
        [python, str(VERIFY), "--work", str(chain_work), "--stage", "labtrust"],
        check=True,
        cwd=ROOT,
    )

    pending = json.loads((chain_work / "science_claim_bundle.pending.json").read_text(encoding="utf-8"))
    assert pending["runtime_receipts"]
    assert pending["certificates"] == []
