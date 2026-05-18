"""PCS QC-release demo runners."""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.workflows.qc_release import FAILURE_CASES, run_failure_demo
from labtrust_gym.pcs.workflows.registry import get_workflow

DEMO_SCENARIOS: dict[str, tuple[str, str]] = {
    "qc-release": ("valid_workflow.yaml", "runs/qc-release"),
    "qc-release-invalid-missing-qc": (
        "invalid_missing_qc.yaml",
        "runs/qc-release-invalid-missing-qc",
    ),
    "qc-release-invalid-unauthorized": (
        "invalid_unauthorized_release.yaml",
        "runs/qc-release-invalid-unauthorized",
    ),
}


def examples_dir(policy_root: Path | None = None) -> Path:
    root = policy_root or get_repo_root()
    return root / "examples" / "pcs_qc_release"


def run_demo(
    demo_name: str,
    *,
    out_dir: Path | None = None,
    policy_root: Path | None = None,
    deterministic: bool | None = None,
) -> Path:
    if demo_name not in DEMO_SCENARIOS:
        raise ValueError(f"unknown demo {demo_name!r}; choose from {list(DEMO_SCENARIOS)}")
    root = policy_root or get_repo_root()
    _, default_rel = DEMO_SCENARIOS[demo_name]

    if demo_name in FAILURE_CASES:
        return run_failure_demo(
            demo_name,
            out_dir=out_dir,
            policy_root=root,
            deterministic=deterministic,
        )

    workflow = get_workflow("qc_release", policy_root=root)
    return workflow.trace_generator()(
        out_dir=out_dir or (root / default_rel),
        policy_root=root,
        deterministic=deterministic,
    )
