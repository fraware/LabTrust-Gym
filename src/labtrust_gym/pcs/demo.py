"""PCS QC-release demo runners."""

from __future__ import annotations

from pathlib import Path

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.deterministic import deterministic_mode, is_deterministic_mode
from labtrust_gym.pcs.workflow import load_workflow_yaml, run_workflow, write_run_directory

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
    yaml_name, default_rel = DEMO_SCENARIOS[demo_name]
    root = policy_root or get_repo_root()
    workflow_path = examples_dir(root) / yaml_name
    workflow = load_workflow_yaml(workflow_path)
    if out_dir is None:
        out_dir = root / default_rel
    use_deterministic = deterministic if deterministic is not None else is_deterministic_mode()
    with deterministic_mode(enabled=use_deterministic):
        result = run_workflow(workflow, policy_root=root)
        write_run_directory(out_dir, result)
    return out_dir
