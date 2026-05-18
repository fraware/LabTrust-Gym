"""
PCS workflow template — subclass PCSWorkflow and register in workflows/registry.py.

Copy into src/<your_package>/pcs/workflows/ or adapt as a standalone package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# When integrated into LabTrust-Gym:
# from labtrust_gym.pcs.workflows.base import PCSWorkflow


class TemplateWorkflow:  # Replace with: class TemplateWorkflow(PCSWorkflow):
    """Placeholder workflow — implement all abstract methods before use."""

    # def __init__(self, *, policy_root: Path | None = None, profile_path: Path | None = None):
    #     super().__init__(policy_root=policy_root, profile_path=profile_path)

    def execute_runtime(self, scratch_dir: Path) -> Path:
        """TODO: Run domain logic; write trace.json under scratch_dir."""
        raise NotImplementedError("implement execute_runtime")

    def export_runtime_receipt(
        self,
        run_dir: Path,
        out_path: Path,
        *,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        """TODO: Map run_dir -> RuntimeReceipt.v0 JSON at out_path."""
        raise NotImplementedError("implement export_runtime_receipt")

    def export_pending_bundle(
        self,
        run_dir: Path,
        out_path: Path,
        *,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        """TODO: Map run_dir -> ScienceClaimBundle.v0 (pending) at out_path."""
        raise NotImplementedError("implement export_pending_bundle")

    def generate_failure_case(self, failure_id: str, out_dir: Path) -> Path:
        """TODO: Build failures/<failure_id>/ with failure_case_manifest.json."""
        raise NotImplementedError("implement generate_failure_case")

    def default_certifyedge_spec(self, certifyedge_root: Path) -> Path:
        """TODO: Point to your CertifyEdge STL spec."""
        return certifyedge_root / "templates" / "your_domain" / "your_workflow.stl"
