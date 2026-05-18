"""QC release PCS workflow — reference WorkflowProfile.v0 implementation for LabTrust."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.deterministic import deterministic_mode, is_deterministic_mode
from labtrust_gym.pcs.export import export_pcs_bundle, export_runtime_receipt
from labtrust_gym.pcs.workflows.base import PCSWorkflow, PcsWorkflowSpec
from labtrust_gym.pcs.workflow import load_workflow_yaml, run_workflow, write_run_directory

DEMO_NAME = "qc-release"
VALID_SCENARIO = "valid_workflow.yaml"
EXAMPLES_REL = "examples/pcs_qc_release"

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


class QcReleaseWorkflow(PCSWorkflow):
    """Hospital lab QC release — LabTrust reference workflow (not a generic template)."""

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

    def examples_dir(self, policy_root: Path | None = None) -> Path:
        return (policy_root or self._policy_root) / EXAMPLES_REL

    def scenario_path(self, policy_root: Path | None = None) -> Path:
        return self.examples_dir(policy_root) / self.spec.scenario_yaml

    def default_certifyedge_spec(self, certifyedge_root: Path) -> Path:
        return certifyedge_root / "templates" / "hospital_lab" / "qc_release.stl"

    def execute_runtime(self, scratch_dir: Path) -> Path:
        workflow_path = self.scenario_path()
        workflow = load_workflow_yaml(workflow_path)
        scratch_dir = scratch_dir.resolve()
        scratch_dir.mkdir(parents=True, exist_ok=True)
        with deterministic_mode(enabled=True):
            result = run_workflow(workflow, policy_root=self._policy_root)
            write_run_directory(scratch_dir, result)
        return scratch_dir

    def export_runtime_receipt(
        self,
        run_dir: Path,
        out_path: Path,
        *,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        return export_runtime_receipt(
            run_dir, out_path, policy_root=policy_root or self._policy_root
        )

    def export_pending_bundle(
        self,
        run_dir: Path,
        out_path: Path,
        *,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        return export_pcs_bundle(
            run_dir, out_path, policy_root=policy_root or self._policy_root
        )

    def trace_generator(self):
        """Back-compat callable for demos and tests."""

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
            return self.export_runtime_receipt(run_dir, out_path, policy_root=policy_root)

        return _export

    def claim_bundle_generator(self):
        def _export(
            run_dir: Path,
            out_path: Path,
            *,
            policy_root: Path | None = None,
        ) -> dict[str, Any]:
            return self.export_pending_bundle(run_dir, out_path, policy_root=policy_root)

        return _export

    def generate_failure_case(self, failure_id: str, out_dir: Path) -> Path:
        from labtrust_gym.pcs.failure_gallery import build_single_failure_case

        out_dir = out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        release = self.examples_dir() / "release"
        build_single_failure_case(
            failure_id,
            out_dir,
            policy_root=self._policy_root,
            release_dir=release,
            profile_path=self._profile.path,
        )
        return out_dir


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
    workflow = load_workflow_yaml(root / EXAMPLES_REL / yaml_name)
    target = out_dir or (root / f"runs/{case_id}")
    use_deterministic = deterministic if deterministic is not None else is_deterministic_mode()
    with deterministic_mode(enabled=use_deterministic):
        result = run_workflow(workflow, policy_root=root)
        write_run_directory(target, result)
    return target.resolve()


def gallery_case_id_for_demo(demo_case_id: str) -> str:
    return _DEMO_TO_GALLERY[demo_case_id]
