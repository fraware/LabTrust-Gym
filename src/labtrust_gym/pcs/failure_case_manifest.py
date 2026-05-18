"""FailureCaseManifest.v0 builders and validators."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from labtrust_gym.pcs.bench_schemas import validate_failure_case_manifest

FAILURE_CASE_MANIFEST_NAME = "failure_case_manifest.json"


@dataclass(frozen=True)
class FailureCaseManifest:
    failure_case_id: str
    workflow_id: str
    expected_failure_code: str
    responsible_component: str
    artifacts: tuple[str, ...]
    repair_hint: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "failure_case_id": self.failure_case_id,
            "workflow_id": self.workflow_id,
            "expected_failure_code": self.expected_failure_code,
            "responsible_component": self.responsible_component,
            "artifacts": sorted(self.artifacts),
            "repair_hint": self.repair_hint,
        }

    def write(self, case_dir: Path) -> Path:
        case_dir = case_dir.resolve()
        path = case_dir / FAILURE_CASE_MANIFEST_NAME
        doc = self.to_dict()
        validate_failure_case_manifest(doc)
        path.write_text(json.dumps(doc, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path


def load_failure_case_manifest(path: Path) -> dict[str, Any]:
    path = path.resolve()
    doc = json.loads(path.read_text(encoding="utf-8"))
    validate_failure_case_manifest(doc)
    return doc
