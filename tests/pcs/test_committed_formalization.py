"""Committed formalization artifacts (pcs-bench / Lean readiness)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from labtrust_gym.pcs.bench_schemas import (
    validate_formalization_readiness_report,
    validate_proof_obligation_hints,
    validate_proof_obligation_identifiers,
)
from labtrust_gym.pcs.formalization import (
    FORMALIZATION_READINESS_REPORT_NAME,
    PROOF_OBLIGATION_HINTS_NAME,
    PROOF_OBLIGATION_IDENTIFIERS_NAME,
)


def test_release_has_formalization_artifacts(release_dir: Path) -> None:
    for name in (
        PROOF_OBLIGATION_HINTS_NAME,
        PROOF_OBLIGATION_IDENTIFIERS_NAME,
        FORMALIZATION_READINESS_REPORT_NAME,
    ):
        path = release_dir / name
        assert path.is_file(), (
            f"missing {name}; run regenerate-release-protocol or "
            "examples/pcs_qc_release/scripts/materialize_formalization_artifacts.py"
        )


def test_committed_formalization_schemas(release_dir: Path) -> None:
    hints = json.loads((release_dir / PROOF_OBLIGATION_HINTS_NAME).read_text(encoding="utf-8"))
    ids_doc = json.loads(
        (release_dir / PROOF_OBLIGATION_IDENTIFIERS_NAME).read_text(encoding="utf-8")
    )
    report = json.loads(
        (release_dir / FORMALIZATION_READINESS_REPORT_NAME).read_text(encoding="utf-8")
    )
    validate_proof_obligation_hints(hints)
    validate_proof_obligation_identifiers(ids_doc)
    validate_formalization_readiness_report(report)
    assert report["formalization_scope"] == "trust_envelope_only"
    assert report["status"] == "passed"
    assert report["all_required_inputs_present"] is True


def test_ci_validate_formalization_script(repo_root: Path) -> None:
    script = repo_root / "examples/pcs_qc_release/scripts/ci_validate_formalization.py"
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
