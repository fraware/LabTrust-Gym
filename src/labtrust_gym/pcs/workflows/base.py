"""PCS workflow abstraction — domain-neutral protocol-native workflow SDK."""

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
from labtrust_gym.pcs.certifyedge_client import invoke_certifyedge_emit_pcs_certificate, resolve_certifyedge_bin
from labtrust_gym.pcs.export import export_trace
from labtrust_gym.pcs.handoff_manifest import (
    HANDOFF_TO_CERTIFYEDGE_NAME,
    HANDOFF_TO_PF_NAME,
    emit_handoff_to_pf,
    write_certifyedge_chain_handoffs,
)
from labtrust_gym.pcs.manifest import resolve_pcs_core_root
from labtrust_gym.pcs.protocol_artifacts import (
    WORKFLOW_PROFILE_RELEASE_NAME,
    ProtocolRegenerationResult,
    assert_protocol_package_complete,
)
from labtrust_gym.pcs.regeneration_report import (
    REGENERATION_REPORT_NAME,
    RegenerationReport,
    RegenerationTimer,
    build_regeneration_report,
    failed_regeneration_report,
    write_regeneration_report,
)
from labtrust_gym.pcs.release_fragment import (
    LABTRUST_RELEASE_FRAGMENT_NAME,
    emit_labtrust_release_fragment,
)
from labtrust_gym.pcs.release_run import (
    promote_release_run_atomic,
    resolve_release_repo_commits,
    write_run_manifests,
)
from labtrust_gym.pcs.workflow_profile import (
    WorkflowProfileView,
    handoff_id_for_kind,
    workflow_profile_view,
)


@dataclass(frozen=True)
class HandoffPolicy:
    """Handoff invariants derived from WorkflowProfile.v0."""

    property_id: str
    certifyedge_handoff_id: str
    pf_handoff_id: str


class PCSWorkflow(ABC):
    """
    Domain-neutral PCS workflow contract.

    Implement ``execute_runtime`` and runtime/bundle exporters; the base class
    implements the shared PCS protocol steps (handoffs, certificate attach, fragment).
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
    def handoff_policy(self) -> HandoffPolicy:
        return HandoffPolicy(
            property_id=self._profile.property_id,
            certifyedge_handoff_id=handoff_id_for_kind(
                self._profile, "runtime_to_certificate"
            ),
            pf_handoff_id=handoff_id_for_kind(self._profile, "bundle_to_verifier"),
        )

    @abstractmethod
    def execute_runtime(self, scratch_dir: Path) -> Path:
        """Run domain logic; return directory containing trace.json and run_meta.json."""

    @abstractmethod
    def export_runtime_receipt(
        self,
        run_dir: Path,
        out_path: Path,
        *,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        """Write RuntimeReceipt.v0 to ``out_path``."""

    @abstractmethod
    def export_pending_bundle(
        self,
        run_dir: Path,
        out_path: Path,
        *,
        policy_root: Path | None = None,
    ) -> dict[str, Any]:
        """Write pending ScienceClaimBundle.v0 to ``out_path``."""

    def generate_runtime_artifacts(self, out_dir: Path) -> list[Path]:
        """Export trace, runtime receipt, and pending bundle into ``out_dir``."""
        out_dir = out_dir.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        scratch = out_dir.parent / f".{self.workflow_id}-runtime-scratch"
        if scratch.exists():
            shutil.rmtree(scratch)
        scratch.mkdir(parents=True)

        run_dir = self.execute_runtime(scratch)
        trace_out = out_dir / "trace.json"
        receipt_out = out_dir / "runtime_receipt.json"
        pending_out = out_dir / "science_claim_bundle.pending.json"

        export_trace(run_dir, trace_out, validate=True)
        from labtrust_gym.pcs.certifyedge_client import normalize_trace_trace_hash

        normalize_trace_trace_hash(trace_out)
        self.export_runtime_receipt(run_dir, receipt_out, policy_root=self._policy_root)
        self.export_pending_bundle(run_dir, pending_out, policy_root=self._policy_root)

        if scratch.exists():
            shutil.rmtree(scratch, ignore_errors=True)

        return [trace_out, receipt_out, pending_out]

    def emit_runtime_to_certificate_handoff(self, out_dir: Path) -> Path:
        """Emit runtime_to_certificate handoff (CertifyEdge chain) under ``out_dir``."""
        out_dir = out_dir.resolve()
        policy = self.handoff_policy
        write_certifyedge_chain_handoffs(
            trace_path=out_dir / "trace.json",
            runtime_receipt_path=out_dir / "runtime_receipt.json",
            work_dir=out_dir,
            policy_root=self._policy_root,
            property_id=policy.property_id,
            handoff_id=policy.certifyedge_handoff_id,
            release_mode=True,
        )
        return out_dir / HANDOFF_TO_CERTIFYEDGE_NAME

    def attach_certificate(self, certificate_path: Path, out_dir: Path) -> Path:
        """Attach ``trace_certificate.json`` to the pending bundle in ``out_dir``."""
        out_dir = out_dir.resolve()
        certificate_path = certificate_path.resolve()
        certified = out_dir / "science_claim_bundle.certified.json"
        attach_certificate_files(
            out_dir / "science_claim_bundle.pending.json",
            certificate_path,
            certified,
        )
        return certified

    def emit_bundle_to_verifier_handoff(self, out_dir: Path) -> Path:
        """Emit bundle_to_verifier handoff under ``out_dir``."""
        out_dir = out_dir.resolve()
        emit_handoff_to_pf(
            bundle_path=out_dir / "science_claim_bundle.certified.json",
            out_path=out_dir / HANDOFF_TO_PF_NAME,
            policy_root=self._policy_root,
            handoff_id=self.handoff_policy.pf_handoff_id,
            release_mode=True,
        )
        return out_dir / HANDOFF_TO_PF_NAME

    def emit_component_release_fragment(self, out_dir: Path) -> Path:
        """Emit the component release fragment JSON under ``out_dir``."""
        out_dir = out_dir.resolve()
        commit = subprocess.check_output(
            ["git", "-C", str(self._policy_root), "rev-parse", "HEAD"],
            text=True,
        ).strip()
        emit_labtrust_release_fragment(
            release_dir=out_dir,
            policy_root=self._policy_root,
            source_commit=commit,
        )
        return out_dir / LABTRUST_RELEASE_FRAGMENT_NAME

    @abstractmethod
    def generate_failure_case(self, failure_id: str, out_dir: Path) -> Path:
        """Build one failure-gallery case directory; return the case root path."""

    def publish_workflow_profile(self, release_dir: Path) -> Path:
        """Copy WorkflowProfile.v0 into the release tree."""
        release_dir = release_dir.resolve()
        dest = release_dir / WORKFLOW_PROFILE_RELEASE_NAME
        shutil.copy2(self._profile.path, dest)
        on_disk = json.loads(dest.read_text(encoding="utf-8"))
        if on_disk.get("workflow_id") != self._profile.workflow_id:
            raise ValueError("published workflow profile workflow_id mismatch")
        return dest

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

        Writes ``regeneration_report.json`` into ``out_dir`` on success or failure.
        """
        root = self._policy_root
        out_dir = out_dir.resolve()
        report_path = out_dir / REGENERATION_REPORT_NAME

        with RegenerationTimer() as timer:
            try:
                result = self._regenerate_protocol_package_impl(
                    out_dir,
                    certifyedge_bin=certifyedge_bin,
                    certifyedge_spec=certifyedge_spec,
                    certifyedge_root=certifyedge_root,
                    pcs_core=pcs_core,
                    run_dir=run_dir,
                )
            except Exception as exc:
                code = type(exc).__name__
                if isinstance(exc, (ValueError, FileNotFoundError)):
                    code = str(exc).split(":", 1)[0].strip() or code
                report = failed_regeneration_report(
                    workflow_id=self.workflow_id,
                    duration_ms=timer.duration_ms,
                    failure_code=code,
                    release_dir=out_dir if out_dir.is_dir() else None,
                )
                write_regeneration_report(report_path, report)
                raise

        report = build_regeneration_report(
            result,
            workflow_id=self.workflow_id,
            duration_ms=timer.duration_ms,
            status="passed",
            failure_code=None,
        )
        write_regeneration_report(report_path, report)
        return result

    def _regenerate_protocol_package_impl(
        self,
        out_dir: Path,
        *,
        certifyedge_bin: str,
        certifyedge_spec: Path | None,
        certifyedge_root: Path | None,
        pcs_core: Path | None,
        run_dir: Path | None,
    ) -> ProtocolRegenerationResult:
        root = self._policy_root
        work = out_dir.parent / ".protocol-regen-staging"
        if work.exists():
            shutil.rmtree(work)
        work.mkdir(parents=True)

        ce_root = certifyedge_root or (root.parent / "CertifyEdge")
        ce_spec = certifyedge_spec or self.default_certifyedge_spec(ce_root)
        if not ce_spec.is_file():
            raise FileNotFoundError(f"CertifyEdge spec not found: {ce_spec}")

        ce_bin = resolve_certifyedge_bin(certifyedge_bin, ce_root)
        ce_commit = subprocess.check_output(
            ["git", "-C", str(ce_root), "rev-parse", "HEAD"],
            text=True,
        ).strip()

        os.environ.setdefault("PCS_DETERMINISTIC", "1")
        os.environ.setdefault("PCS_RELEASE_FIXTURE", "1")
        os.environ["CERTIFYEDGE_SOURCE_COMMIT"] = ce_commit

        demo_run = run_dir
        if demo_run is None:
            scratch = work / ".runtime-run"
            demo_run = self.execute_runtime(scratch)
        else:
            if demo_run.exists():
                shutil.rmtree(demo_run)
            demo_run = self.execute_runtime(demo_run)

        self.generate_runtime_artifacts(work)

        cert_path = work / "trace_certificate.json"
        self.emit_runtime_to_certificate_handoff(work)
        invoke_certifyedge_emit_pcs_certificate(
            ce_bin,
            spec=ce_spec,
            trace_path=work / "trace.json",
            out_path=cert_path,
            handoff_path=work / HANDOFF_TO_CERTIFYEDGE_NAME,
            env={"CERTIFYEDGE_SOURCE_COMMIT": ce_commit},
            certifyedge_root=ce_root,
        )
        from labtrust_gym.pcs.certifyedge_client import normalize_certifyedge_certificate_provenance

        normalize_certifyedge_certificate_provenance(cert_path, source_commit=ce_commit)
        subprocess.run(["pcs", "validate", str(cert_path)], check=True, cwd=root)
        subprocess.run(
            [ce_bin, "verify-certificate", str(cert_path), "--trace", str(work / "trace.json")],
            check=True,
        )

        self.attach_certificate(cert_path, work)
        subprocess.run(
            ["pcs", "validate", str(work / "science_claim_bundle.certified.json")],
            check=True,
            cwd=root,
        )

        self.emit_bundle_to_verifier_handoff(work)

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
        self.emit_runtime_to_certificate_handoff(work)
        self.emit_bundle_to_verifier_handoff(work)

        os.environ["CERTIFYEDGE_ROOT"] = str(ce_root)
        os.environ["CERTIFYEDGE_BIN"] = ce_bin
        os.environ["CERTIFYEDGE_SPEC"] = str(ce_spec)

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
        self.emit_component_release_fragment(out_dir)
        self.publish_workflow_profile(out_dir)

        from labtrust_gym.pcs.release_fixtures import write_trace_hash_alignment

        write_trace_hash_alignment(out_dir)

        assert_protocol_package_complete(out_dir)
        if not (out_dir / WORKFLOW_PROFILE_RELEASE_NAME).is_file():
            raise FileNotFoundError(f"missing published {WORKFLOW_PROFILE_RELEASE_NAME}")

        from labtrust_gym.pcs.verify_release_protocol import verify_release_protocol

        checks = verify_release_protocol(out_dir, policy_root=root)

        if work.exists():
            shutil.rmtree(work, ignore_errors=True)

        return ProtocolRegenerationResult(
            release_dir=out_dir,
            run_dir=demo_run,
            checks=checks,
            commits=commits,
        )

    def default_certifyedge_spec(self, certifyedge_root: Path) -> Path:
        """Override when the CertifyEdge STL path is not workflow-specific."""
        return certifyedge_root / "templates" / "hospital_lab" / "qc_release.stl"

    # --- Back-compat aliases (pre-Phase-4 names) ---

    def generate_trace(
        self,
        *,
        out_dir: Path | None = None,
        policy_root: Path | None = None,
        deterministic: bool | None = None,
    ) -> Path:
        del policy_root, deterministic
        target = out_dir or (self._policy_root / "runs" / f"{self.workflow_id}-run")
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        return self.execute_runtime(target)

    def export_protocol_inputs(
        self,
        run_dir: Path,
        work_dir: Path,
        *,
        policy_root: Path | None = None,
    ) -> dict[str, Path]:
        """Export trace, receipt, and pending bundle from an existing run directory."""
        work_dir = work_dir.resolve()
        run_dir = run_dir.resolve()
        work_dir.mkdir(parents=True, exist_ok=True)
        root = policy_root or self._policy_root

        trace_out = work_dir / "trace.json"
        receipt_out = work_dir / "runtime_receipt.json"
        pending_out = work_dir / "science_claim_bundle.pending.json"

        export_trace(run_dir, trace_out, validate=True)
        from labtrust_gym.pcs.certifyedge_client import normalize_trace_trace_hash

        normalize_trace_trace_hash(trace_out)
        self.export_runtime_receipt(run_dir, receipt_out, policy_root=root)
        self.export_pending_bundle(run_dir, pending_out, policy_root=root)

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
        del policy_root, release_mode
        path = self.emit_runtime_to_certificate_handoff(work_dir)
        return json.loads(path.read_text(encoding="utf-8"))

    def emit_handoff_to_pf(
        self,
        work_dir: Path,
        *,
        policy_root: Path | None = None,
        release_mode: bool = True,
    ) -> dict[str, Any]:
        del policy_root, release_mode
        path = self.emit_bundle_to_verifier_handoff(work_dir)
        return json.loads(path.read_text(encoding="utf-8"))

    def emit_release_fragment(
        self,
        release_dir: Path,
        *,
        policy_root: Path | None = None,
        source_commit: str | None = None,
    ) -> dict[str, Any]:
        del policy_root
        if source_commit is not None:
            emit_labtrust_release_fragment(
                release_dir=release_dir,
                policy_root=self._policy_root,
                source_commit=source_commit,
            )
        else:
            self.emit_component_release_fragment(release_dir)
        path = release_dir / LABTRUST_RELEASE_FRAGMENT_NAME
        return json.loads(path.read_text(encoding="utf-8"))


# Back-compat alias
PcsWorkflow = PCSWorkflow


@dataclass(frozen=True)
class PcsWorkflowSpec:
    """Optional demo routing metadata (reference QC workflow only)."""

    workflow_id: str
    property_id: str
    demo_name: str
    scenario_yaml: str
    success_case: str
    failure_cases: tuple[str, ...] = ()
    expected_certificates: tuple[str, ...] = ("TraceCertificate.v0",)
    limitations_notice: str = ""
    default_run_rel: str = "runs/qc-release"
