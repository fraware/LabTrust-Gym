"""
Specimen lifecycle and reception acceptance rules.

Specimens move through states: arrived_at_reception, accessioning, accepted,
held, rejected. Actions include CREATE_ACCESSION, CHECK_ACCEPTANCE_RULES,
ACCEPT_SPECIMEN, REJECT_SPECIMEN, HOLD_SPECIMEN. Rejection and hold reasons
are encoded as reason codes: e.g. ID mismatch (ID_MISMATCH), leaking (INT_LEAKING),
citrate underfill (CNT_CITRATE_FILL_INVALID). HOLD_SPECIMEN must include a
reason_code or the action is BLOCKED (AUDIT_MISSING_REASON_CODE). BLOCKED
actions do not change specimen state.
"""

from __future__ import annotations

from typing import Any

ID_MISMATCH = "ID_MISMATCH"
INT_LEAKING = "INT_LEAKING"
CNT_CITRATE_FILL_INVALID = "CNT_CITRATE_FILL_INVALID"
AUDIT_MISSING_REASON_CODE = "AUDIT_MISSING_REASON_CODE"
INV_COAG_FILL_001 = "INV-COAG-FILL-001"

# Default templates from golden suite fixtures (when template_ref is used).
DEFAULT_TEMPLATES: dict[str, dict[str, Any]] = {
    "S_BIOCHEM_OK": {
        "specimen_id": "S1",
        "patient_identifiers_hash": "pid:hash:001",
        "collection_ts_s": 0,
        "arrival_ts_s": 600,
        "panel_id": "BIOCHEM_PANEL_CORE",
        "container_type": "SERUM_SST",
        "specimen_type": "SERUM",
        "integrity_flags": {
            "leak": False,
            "clot": False,
            "hemolysis": False,
            "insufficient_volume": False,
            "label_issue": False,
        },
        "fill_ratio_ok": None,
        "hazard_flag": False,
        "separated_ts_s": None,
        "temp_band": "AMBIENT_20_25",
        "status": "arrived_at_reception",
    },
    "S_COAG_OK": {
        "specimen_id": "S2",
        "patient_identifiers_hash": "pid:hash:002",
        "collection_ts_s": 0,
        "arrival_ts_s": 600,
        "panel_id": "COAG_PANEL_CORE",
        "container_type": "PLASMA_CITRATE",
        "specimen_type": "PLASMA",
        "integrity_flags": {
            "leak": False,
            "clot": False,
            "hemolysis": False,
            "insufficient_volume": False,
            "label_issue": False,
        },
        "fill_ratio_ok": True,
        "hazard_flag": False,
        "separated_ts_s": None,
        "temp_band": "AMBIENT_20_25",
        "status": "arrived_at_reception",
    },
}


def _expand_specimen(
    entry: dict[str, Any],
    templates: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Expand template_ref to full specimen dict; else copy with status/last_reason_code."""
    templates = templates or DEFAULT_TEMPLATES
    if "template_ref" in entry:
        ref = entry["template_ref"]
        spec = dict(templates.get(ref, {}))
        spec["specimen_id"] = spec.get("specimen_id", ref)
        spec["status"] = spec.get("status", "arrived_at_reception")
        spec["last_reason_code"] = None
        return spec
    spec = dict(entry)
    spec.setdefault("status", "arrived_at_reception")
    spec.setdefault("last_reason_code", None)
    return spec


class SpecimenStore:
    """
    Specimen state and acceptance check cache.
    - specimens: specimen_id -> { status, last_reason_code, ...attrs }
    - last_id_match: specimen_id -> bool | None (from last CHECK_ACCEPTANCE_RULES).
    """

    def __init__(self, templates: dict[str, dict[str, Any]] | None = None) -> None:
        self._specimens: dict[str, dict[str, Any]] = {}
        self._last_id_match: dict[str, bool | None] = {}
        self._templates = templates or dict(DEFAULT_TEMPLATES)
        self._aliquot_to_specimen: dict[str, str] = {}

    def load_initial(self, specimens: list[dict[str, Any]]) -> None:
        """Load specimens from initial_state; expand template_ref."""
        self._specimens = {}
        self._last_id_match = {}
        self._aliquot_to_specimen = {}
        for entry in specimens or []:
            spec = _expand_specimen(entry, self._templates)
            sid = spec.get("specimen_id")
            if sid:
                self._specimens[str(sid)] = spec

    def add_specimen(self, entry: dict[str, Any]) -> bool:
        """Add one specimen at runtime (e.g. INJECT_SPECIMEN for golden shift-change). Returns True if added."""
        spec = _expand_specimen(entry, self._templates)
        sid = spec.get("specimen_id")
        if not sid:
            return False
        if sid in self._specimens:
            return False
        self._specimens[str(sid)] = spec
        return True

    def get(self, specimen_id: str) -> dict[str, Any] | None:
        return self._specimens.get(specimen_id)

    def set_separated_ts(self, specimen_id: str, t_s: int) -> bool:
        """Set separated_ts_s for specimen (from CENTRIFUGE_END)."""
        if specimen_id not in self._specimens:
            return False
        self._specimens[specimen_id]["separated_ts_s"] = t_s
        return True

    def record_aliquot(self, aliquot_id: str, specimen_id: str) -> None:
        """Record aliquot_id -> specimen_id (from ALIQUOT_CREATE)."""
        self._aliquot_to_specimen[str(aliquot_id)] = str(specimen_id)

    def resolve_to_specimen_ids(
        self,
        specimen_ids: list[str] | None = None,
        aliquot_ids: list[str] | None = None,
    ) -> list[str]:
        """Resolve specimen_ids or aliquot_ids to list of specimen_ids."""
        if specimen_ids:
            return [str(s) for s in specimen_ids]
        if aliquot_ids:
            out = []
            for a in aliquot_ids:
                sid = self._aliquot_to_specimen.get(str(a), str(a))
                if sid in self._specimens or sid:
                    out.append(sid)
            return out
        return []

    def specimen_status(self, specimen_id: str) -> str | None:
        spec = self._specimens.get(specimen_id)
        return spec.get("status") if spec else None

    def get_status_counts(self) -> dict[str, int]:
        """Return counts of specimens per status (for observation)."""
        counts: dict[str, int] = {}
        for spec in self._specimens.values():
            st = spec.get("status") or "unknown"
            counts[st] = counts.get(st, 0) + 1
        return counts

    def list_specimen_ids_by_status(self, status: str) -> list[str]:
        """Return specimen_ids with the given status. Deterministic order (sorted)."""
        out = [
            sid
            for sid, spec in self._specimens.items()
            if (spec.get("status") or "") == status
        ]
        return sorted(out)

    def last_reason_code(self, specimen_id: str) -> str | None:
        spec = self._specimens.get(specimen_id)
        return spec.get("last_reason_code") if spec else None

    def create_accession(self, specimen_id: str) -> bool:
        """Set status to accessioning. Returns True if specimen exists."""
        spec = self._specimens.get(specimen_id)
        if not spec:
            return False
        spec["status"] = "accessioning"
        return True

    def check_acceptance_rules(
        self, specimen_id: str, id_match: bool | None = None
    ) -> bool:
        """Store id_match for specimen (from args). True if specimen exists."""
        if specimen_id not in self._specimens:
            return False
        self._last_id_match[specimen_id] = id_match
        return True

    def accept_specimen(
        self,
        specimen_id: str,
    ) -> tuple[str, list[str], str | None, list[dict[str, str]]]:
        """
        Apply acceptance rules. Returns (outcome, emits, blocked_reason_code, violations).
        outcome: "ACCEPTED" | "REJECTED" | "HELD"
        - ID mismatch (last_id_match is False) => REJECTED, REJECT_SPECIMEN,
          ID_MISMATCH.
        - Leaking (integrity_flags.leak or hazard_flag) => REJECTED,
          REJECT_SPECIMEN, INT_LEAKING.
        - Citrate underfill (container citrate and fill_ratio_ok is False) =>
          HELD, HOLD_SPECIMEN, CNT_CITRATE_FILL_INVALID, INV-COAG-FILL-001.
        - Else => ACCEPTED, emits ACCEPT_SPECIMEN.
        Mutates state only when outcome is not BLOCKED.
        """
        spec = self._specimens.get(specimen_id)
        if not spec:
            return "ACCEPTED", ["ACCEPT_SPECIMEN"], None, []

        id_match = self._last_id_match.get(specimen_id)
        if id_match is False:
            spec["status"] = "rejected"
            spec["last_reason_code"] = ID_MISMATCH
            return "ACCEPTED", ["REJECT_SPECIMEN"], None, []

        flags = spec.get("integrity_flags") or {}
        if flags.get("leak") or spec.get("hazard_flag"):
            spec["status"] = "rejected"
            spec["last_reason_code"] = INT_LEAKING
            return "ACCEPTED", ["REJECT_SPECIMEN"], None, []

        container = (spec.get("container_type") or "").upper()
        fill_ok = spec.get("fill_ratio_ok")
        if "CITRATE" in container and fill_ok is False:
            spec["status"] = "held"
            spec["last_reason_code"] = CNT_CITRATE_FILL_INVALID
            return (
                "ACCEPTED",
                ["HOLD_SPECIMEN"],
                None,
                [
                    {"invariant_id": INV_COAG_FILL_001, "status": "VIOLATION"},
                ],
            )

        spec["status"] = "accepted"
        spec["last_reason_code"] = None
        return "ACCEPTED", ["ACCEPT_SPECIMEN"], None, []

    def reject_specimen(self, specimen_id: str, reason_code: str | None) -> bool:
        if specimen_id not in self._specimens:
            return False
        self._specimens[specimen_id]["status"] = "rejected"
        self._specimens[specimen_id]["last_reason_code"] = reason_code
        return True

    def hold_specimen(
        self, specimen_id: str, reason_code: str | None
    ) -> tuple[bool, str | None]:
        """
        Hold specimen with reason_code. Returns (ok, blocked_reason_code).
        If reason_code is None/empty => (False, AUDIT_MISSING_REASON_CODE),
        do not mutate.
        """
        if not reason_code or not str(reason_code).strip():
            return False, AUDIT_MISSING_REASON_CODE
        if specimen_id not in self._specimens:
            return False, None
        self._specimens[specimen_id]["status"] = "held"
        self._specimens[specimen_id]["last_reason_code"] = reason_code
        return True, None
