"""QC release PCS workflow (hospital_lab.qc_release) — reference WorkflowProfile.v0 implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.deterministic import deterministic_mode, is_deterministic_mode
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt
from labtrust_gym.pcs.workflows.base import PcsWorkflow, PcsWorkflowSpec
from labtrust_gym.pcs.workflow import load_workflow_yaml, run_workflow, write_run_directory

DEMO_NAME = "qc-release"
VALID_SCENARIO = "valid_workflow.yaml"

FAILURE_CASES: tuple[str, ...] = (
    "qc-release-invalid-missing-qc",
    "qc-release-invalid-unauthorized",
)

_FAILURE_YAML: dict[str, str] = {
    "qc-release-invalid-missing-qc": "invalid_missing_qc.yaml",
    "qc-release-invalid-unauthorized": "invalid_unauthorized_release.yaml",
}

_DEMO_TO_GALLERY: dict[str, str] = {
    "qc-release-invalid-missing-qc": "missing_qc_result",
    "qc-release-invalid-unauthorized": "unauthorized_release",
}


class QcReleaseWorkflow(PcsWorkflow):
    """Hospital lab QC release — exemplary reference workflow for WorkflowProfile.v0."""

    @property
    def spec(self) -> PcsWorkflowSpec:
        return PcsWorkflowSpec(
            workflow_id=self._profile.workflow_id,
            property_id=self._profile.property_id,
            demo_name=DEMO_NAME,
            scenario_yaml=VALID_SCENARIO,
            success_case=DEMO_NAME,
            failure_cases=FAILURE_CASES,
            expected_certificates=self._profile.certificate_artifacts,
            limitations_notice=self._profile.limitations_notice,
            default_run_rel="runs/qc-release",
        )

    def generate_trace(
        self,
        *,
        out_dir: Path | None = None,
        policy_root: Path | None = None,
        deterministic: bool | None = None,
    ) -> Path:
        return self.trace_generator()(
            out_dir=out_dir,
            policy_root=policy_root,
            deterministic=deterministic,
        )

    def trace_generator(self):
        def _run(
            *,
            out_dir: Path | None = None,
            policy_root: Path | None = None,
            deterministic: bool | None = None,
        ) -> Path:
            root = policy_root or self._policy_root
            workflow_path = self.scenario_path(root)
            workflow = load_workflow_yaml(workflow_path)
            target = out_dir or (root / self.spec.default_run_rel)
            use_deterministic = (
                deterministic if deterministic is not None else is_deterministic_mode()
            )
            with deterministic_mode(enabled=use_deterministic):
                result = run_workflow(workflow, policy_root=root)
                write_run_directory(target, result)
            return target.resolve()

        return _run

    def runtime_receipt_generator(self):
        def _export(
            run_dir: Path,
            out_path: Path,
            *,
            policy_root: Path | None = None,
        ) -> dict[str, Any]:
            return export_runtime_receipt(
                run_dir, out_path, policy_root=policy_root or self._policy_root
            )

        return _export

    def claim_bundle_generator(self):
        def _export(
            run_dir: Path,
            out_path: Path,
            *,
            policy_root: Path | None = None,
        ) -> dict[str, Any]:
            return export_pcs_bundle(
                run_dir, out_path, policy_root=policy_root or self._policy_root
            )

        return _export

    def generate_failure_case(
        self,
        case_id: str,
        *,
        artifacts_dir: Path,
        policy_root: Path | None = None,
        release_baseline: Path | None = None,
    ) -> list[str]:
        from labtrust_gym.pcs.failure_gallery import build_single_failure_case

        root = policy_root or self._policy_root
        release = release_baseline or (self.examples_dir(root) / "release")
        case_dir = artifacts_dir.parent if artifacts_dir.name == "artifacts" else artifacts_dir
        return build_single_failure_case(
            case_id,
            case_dir,
            policy_root=root,
            release_dir=release,
            profile_path=self._profile.path,
        )


def run_failure_demo(
    case_id: str,
    *,
    out_dir: Path | None = None,
    policy_root: Path | None = None,
    deterministic: bool | None = None,
) -> Path:
    """Run a registered QC-release failure scenario (missing QC, unauthorized release)."""
    if case_id not in FAILURE_CASES:
        raise ValueError(f"unknown failure case {case_id!r}; choose from {list(FAILURE_CASES)}")
    root = policy_root or get_repo_root()
    yaml_name = _FAILURE_YAML[case_id]
    workflow = load_workflow_yaml(root / "examples" / "pcs_qc_release" / yaml_name)
    target = out_dir or (root / f"runs/{case_id}")
    use_deterministic = deterministic if deterministic is not None else is_deterministic_mode()
    with deterministic_mode(enabled=use_deterministic):
        result = run_workflow(workflow, policy_root=root)
        write_run_directory(target, result)
    return target.resolve()


def gallery_case_id_for_demo(demo_case_id: str) -> str:
    return _DEMO_TO_GALLERY[demo_case_id]
