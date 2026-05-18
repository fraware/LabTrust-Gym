"""PCS workflow abstraction — reference template for protocol-native workflows."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labtrust_gym.config import get_repo_root
from labtrust_gym.pcs.attach_certificate import attach_certificate_files
from labtrust_gym.pcs.export import export_trace
from labtrust_gym.pcs.handoff_manifest import (
    HANDOFF_TO_CERTIFYEDGE_NAME,
    HANDOFF_TO_PF_NAME,
    emit_handoff_to_pf,
    write_certifyedge_chain_handoffs,
)
from labtrust_gym.pcs.manifest import resolve_pcs_core_root
from labtrust_gym.pcs.release_fragment import (
    LABTRUST_RELEASE_FRAGMENT_NAME,
    emit_labtrust_release_fragment,
)
from labtrust_gym.pcs.certifyedge_client import invoke_certifyedge_emit_pcs_certificate
from labtrust_gym.pcs.release_run import (
    promote_release_run_atomic,
    resolve_release_repo_commits,
    write_run_manifests,
)
from labtrust_gym.pcs.verify_release_protocol import verify_release_protocol
from labtrust_gym.pcs.workflow_profile import (
    WorkflowProfileView,
    handoff_id_for_kind,
    workflow_profile_view,
)

from labtrust_gym.pcs.protocol_artifacts import (
    WORKFLOW_PROFILE_RELEASE_NAME,
    ProtocolRegenerationResult,
    assert_protocol_package_complete,
)


@dataclass(frozen=True)
class HandoffPolicy:
    """Handoff invariants derived from WorkflowProfile.v0."""

    property_id: str
    certifyedge_handoff_id: str
    pf_handoff_id: str


@dataclass(frozen=True)
class PcsWorkflowSpec:
    """Workflow metadata mirrored from WorkflowProfile.v0 + demo routing."""

    workflow_id: str
    property_id: str
    demo_name: str
    scenario_yaml: str
    success_case: str
    failure_cases: tuple[str, ...] = ()
    expected_certificates: tuple[str, ...] = ("TraceCertificate.v0",)
    limitations_notice: str = ""
    default_run_rel: str = "runs/qc-release"


class PcsWorkflow(ABC):
    """
    Protocol-native PCS workflow contract.

    Domain workflows implement scenario execution; this base class owns the
    shared PCS protocol steps (handoffs, certificate attach, fragment).
    """

    def __init__(
        self,
        *,
        policy_root: Path | None = None,
        profile_path: Path | None = None,
    ) -> None:
        self._policy_root = policy_root or get_repo_root()
        self._profile = workflow_profile_view(profile_path, policy_root=self._policy_root)

    @property
    def profile(self) -> WorkflowProfileView:
        return self._profile

    @property
    def workflow_id(self) -> str:
        return self._profile.workflow_id

    @property
    def profile_path(self) -> Path:
        return self._profile.path

    @property
    @abstractmethod
    def spec(self) -> PcsWorkflowSpec:
        """Workflow demo routing metadata."""

    @property
    def handoff_policy(self) -> HandoffPolicy:
        return HandoffPolicy(
            property_id=self._profile.property_id,
            certifyedge_handoff_id=handoff_id_for_kind(
                self._profile, "runtime_to_certificate"
            ),
            pf_handoff_id=handoff_id_for_kind(self._profile, "bundle_to_verifier"),
        )

    @abstractmethod
    def generate_trace(
        self,
        *,
        out_dir: Path | None = None,
        policy_root: Path | None = None,
        deterministic: bool | None = None,
    ) -> Path:
        """Run domain workflow and return run directory containing trace.json."""

    def generate_runtime_receipt(
        self,
        run_dir: Path,
        out_path: Path,
        *,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        return self.runtime_receipt_generator()(run_dir, out_path, policy_root=policy_root)

    def generate_pending_bundle(
        self,
        run_dir: Path,
        out_path: Path,
        *,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        return self.claim_bundle_generator()(run_dir, out_path, policy_root=policy_root)

    @abstractmethod
    def runtime_receipt_generator(self):
        """Return callable ``(run_dir, out_path) -> RuntimeReceipt.v0``."""

    @abstractmethod
    def claim_bundle_generator(self):
        """Return callable ``(run_dir, out_path) -> ScienceClaimBundle.v0`` (pending)."""

    def export_protocol_inputs(
        self,
        run_dir: Path,
        work_dir: Path,
        *,
        policy_root: Path | None = None,
    ) -> dict[str, Path]:
        """Export trace, runtime receipt, and pending bundle into ``work_dir``."""
        work_dir = work_dir.resolve()
        run_dir = run_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)

        trace_out = work_dir / "trace.json"
        receipt_out = work_dir / "runtime_receipt.json"
        pending_out = work_dir / "science_claim_bundle.pending.json"

        export_trace(run_dir, trace_out, validate=True)
        from labtrust_gym.pcs.certifyedge_client import normalize_trace_trace_hash

        normalize_trace_trace_hash(trace_out)
        self.generate_runtime_receipt(run_dir, receipt_out, policy_root=policy_root)
        self.generate_pending_bundle(run_dir, pending_out, policy_root=policy_root)

        return {
            "trace": trace_out,
            "runtime_receipt": receipt_out,
            "pending_bundle": pending_out,
        }

    def emit_handoff_to_certifyedge(
        self,
        work_dir: Path,
        *,
        policy_root: Path | None = None,
        release_mode: bool = True,
    ) -> dict[str, Any]:
        root = policy_root or self._policy_root
        policy = self.handoff_policy
        return write_certifyedge_chain_handoffs(
            trace_path=work_dir / "trace.json",
            runtime_receipt_path=work_dir / "runtime_receipt.json",
            work_dir=work_dir,
            policy_root=root,
            property_id=policy.property_id,
            handoff_id=policy.certifyedge_handoff_id,
            release_mode=release_mode,
        )

    def attach_certificate(
        self,
        work_dir: Path,
        certificate_path: Path,
        *,
        pending_name: str = "science_claim_bundle.pending.json",
        certified_name: str = "science_claim_bundle.certified.json",
    ) -> dict[str, Any]:
        pending = work_dir / pending_name
        certified = work_dir / certified_name
        return attach_certificate_files(pending, certificate_path, certified)

    def emit_handoff_to_pf(
        self,
        work_dir: Path,
        *,
        policy_root: Path | None = None,
        release_mode: bool = True,
    ) -> dict[str, Any]:
        return emit_handoff_to_pf(
            bundle_path=work_dir / "science_claim_bundle.certified.json",
            out_path=work_dir / HANDOFF_TO_PF_NAME,
            policy_root=policy_root or self._policy_root,
            handoff_id=self.handoff_policy.pf_handoff_id,
            release_mode=release_mode,
        )

    def emit_release_fragment(
        self,
        release_dir: Path,
        *,
        policy_root: Path | None = None,
        source_commit: str | None = None,
    ) -> dict[str, Any]:
        root = policy_root or self._policy_root
        commit = source_commit
        if commit is None:
            commit = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                text=True,
            ).strip()
        return emit_labtrust_release_fragment(
            release_dir=release_dir,
            policy_root=root,
            source_commit=commit,
        )

    def publish_workflow_profile(self, release_dir: Path) -> Path:
        """Copy WorkflowProfile.v0 into the release tree (profile-driven generation)."""
        release_dir = release_dir.resolve()
        dest = release_dir / WORKFLOW_PROFILE_RELEASE_NAME
        shutil.copy2(self._profile.path, dest)
        on_disk = json.loads(dest.read_text(encoding="utf-8"))
        if on_disk.get("workflow_id") != self._profile.workflow_id:
            raise ValueError("published workflow profile workflow_id mismatch")
        return dest

    @abstractmethod
    def generate_failure_case(
        self,
        case_id: str,
        *,
        artifacts_dir: Path,
        policy_root: Path | None = None,
        release_baseline: Path | None = None,
    ) -> list[str]:
        """Build one failure-gallery case under ``artifacts_dir``; return artifact names."""

    def examples_dir(self, policy_root: Path) -> Path:
        return policy_root / "examples" / "pcs_qc_release"

    def scenario_path(self, policy_root: Path) -> Path:
        return self.examples_dir(policy_root) / self.spec.scenario_yaml

    def regenerate_protocol_package(
        self,
        out_dir: Path,
        *,
        certifyedge_bin: str = "certifyedge",
        certifyedge_spec: Path | None = None,
        certifyedge_root: Path | None = None,
        pcs_core: Path | None = None,
        run_dir: Path | None = None,
    ) -> ProtocolRegenerationResult:
        """
        Clean-run PCS protocol regeneration (no fixture copying).

        Produces all ``LABTRUST_PROTOCOL_PACKAGE_ARTIFACTS`` plus ``workflow_profile.v0.json``.
        """
        root = self._policy_root
        out_dir = out_dir.resolve()
        work = out_dir.parent / ".protocol-regen-staging"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)

        ce_root = certifyedge_root or (root.parent / "CertifyEdge")
        ce_spec = certifyedge_spec or (ce_root / "templates" / "hospital_lab" / "qc_release.stl")
        if not ce_spec.is_file():
            raise FileNotFoundError(f"CertifyEdge spec not found: {ce_spec}")

        from labtrust_gym.pcs.certifyedge_client import resolve_certifyedge_bin

        ce_bin = resolve_certifyedge_bin(certifyedge_bin, ce_root)
        ce_commit = subprocess.check_output(
            ["git", "-C", str(ce_root), "rev-parse", "HEAD"],
            text=True,
        ).strip()

        os.environ.setdefault("PCS_DETERMINISTIC", "1")
        os.environ.setdefault("PCS_RELEASE_FIXTURE", "1")
        os.environ["CERTIFYEDGE_SOURCE_COMMIT"] = ce_commit

        demo_run = run_dir or (root / "runs" / f"{self.spec.demo_name}-protocol-regen")
        if demo_run.exists():
            shutil.rmtree(demo_run)
        demo_run = self.generate_trace(
            out_dir=demo_run,
            policy_root=root,
            deterministic=True,
        )
        self.export_protocol_inputs(demo_run, work, policy_root=root)

        cert_path = work / "trace_certificate.json"
        handoff_doc = self.emit_handoff_to_certifyedge(work, policy_root=root, release_mode=True)
        invoke_certifyedge_emit_pcs_certificate(
            ce_bin,
            spec=ce_spec,
            trace_path=work / "trace.json",
            out_path=cert_path,
            handoff_path=work / HANDOFF_TO_CERTIFYEDGE_NAME,
            env={"CERTIFYEDGE_SOURCE_COMMIT": ce_commit},
            certifyedge_root=ce_root,
        )
        subprocess.run(["pcs", "validate", str(cert_path)], check=True, cwd=root)
        subprocess.run(
            [ce_bin, "verify-certificate", str(cert_path), "--trace", str(work / "trace.json")],
            check=True,
        )

        self.attach_certificate(work, cert_path)
        subprocess.run(
            ["pcs", "validate", str(work / "science_claim_bundle.certified.json")],
            check=True,
            cwd=root,
        )

        self.emit_handoff_to_pf(work, policy_root=root, release_mode=True)

        if pcs_core is not None and (pcs_core / "trace.json").is_file():
            pcs_git_root = resolve_pcs_core_root(root)
        elif pcs_core is not None:
            pcs_git_root = pcs_core.resolve()
        else:
            pcs_git_root = resolve_pcs_core_root(root)
        commits = resolve_release_repo_commits(
            root,
            certifyedge_root=ce_root,
            pcs_core_root=pcs_git_root,
        )
        policy = self.handoff_policy
        write_run_manifests(
            work,
            commits,
            generator="regenerate_release_protocol",
            handoff_id=policy.pf_handoff_id,
            certifyedge_handoff_id=policy.certifyedge_handoff_id,
            pf_handoff_id=policy.pf_handoff_id,
            property_id=policy.property_id,
        )
        self.emit_handoff_to_certifyedge(work, policy_root=root, release_mode=True)
        self.emit_handoff_to_pf(work, policy_root=root, release_mode=True)

        os.environ["CERTIFYEDGE_ROOT"] = str(ce_root)
        os.environ["CERTIFYEDGE_BIN"] = ce_bin
        os.environ["CERTIFYEDGE_SPEC"] = str(ce_spec)

        # LabTrust protocol regen does not re-run PF/SM; drop stale downstream artifacts.
        for stale_name in (
            "verification_result.json",
            "signed_science_claim_bundle.json",
            "scientific_memory_import_report.json",
        ):
            stale = out_dir / stale_name
            if stale.is_file():
                stale.unlink()

        promote_release_run_atomic(
            work,
            out_dir,
            generator="regenerate_release_protocol",
            certifyedge_bin=ce_bin,
            certifyedge_spec=str(ce_spec),
        )
        self.emit_release_fragment(out_dir, policy_root=root, source_commit=commits["labtrust_gym_commit"])
        self.publish_workflow_profile(out_dir)

        from labtrust_gym.pcs.release_fixtures import write_trace_hash_alignment

        write_trace_hash_alignment(out_dir)

        assert_protocol_package_complete(out_dir)
        if not (out_dir / WORKFLOW_PROFILE_RELEASE_NAME).is_file():
            raise FileNotFoundError(f"missing published {WORKFLOW_PROFILE_RELEASE_NAME}")

        # LabTrust protocol checks only; pcs-core RC gate is ``verify-release-protocol --pcs-core``.
        checks = verify_release_protocol(out_dir, policy_root=root)

        if work.exists():
            shutil.rmtree(work, ignore_errors=True)

        return ProtocolRegenerationResult(
            release_dir=out_dir,
            run_dir=demo_run,
            checks=checks,
            commits=commits,
        )
