# FHIR R4 Export

See [Frozen contracts](../contracts/frozen_contracts.md) and [Release checklist](../operations/release_checklist.md) for verifying an EvidenceBundle.v0.1 (including integrity, schema, hashchain, and invariant trace) with `labtrust verify-bundle --bundle <dir>`.

The FHIR R4 exporter converts **Receipt.v0.1** (from an evidence bundle or receipts directory) into **valid HL7 FHIR R4 JSON**. The repo targets valid FHIR R4: no placeholder IDs, and missing data is represented using the standard **data-absent-reason** extension and `Observation.dataAbsentReason` where appropriate.

- **Bundle**: type = `collection`; contains Specimen (when present), Observation(s), and DiagnosticReport.
- **When specimen is missing**: No Specimen resource is emitted; `Observation.specimen` and `DiagnosticReport.specimen` are set to a Reference object containing only the data-absent-reason extension (`valueCode`: `unknown`).
- **When Observation has no numeric value**: `value[x]` is omitted; `Observation.dataAbsentReason` is populated with the HL7 data-absent-reason code system and code `unknown`.
- **IDs**: All resource ids are deterministic (specimen_id or content-addressed hash; result_id or index-based); in-bundle references resolve. No `id="placeholder"` or `Specimen/placeholder` is ever emitted.

No external FHIR libraries are required; output is pure JSON with lightweight structural validation.

## CLI

```bash
labtrust export-fhir --receipts <dir> --out <dir> [--filename fhir_bundle.json]
```

- **--receipts**: Directory containing receipt files (e.g. `EvidenceBundle.v0.1/` with `receipt_*.v0.1.json`) or any folder with `receipt_*.v0.1.json`. If `manifest.json` is present, `partner_id` and `policy_fingerprint` are read and added to the bundle meta.
- **--out**: Output directory; the FHIR bundle JSON is written here.
- **--filename**: Output filename (default: `fhir_bundle.json`).

## Mapping rules

| Receipt field | FHIR resource / path | Notes |
|---------------|----------------------|--------|
| specimen_id | Specimen.id, Specimen.identifier | id = specimen_id when present; otherwise deterministic content-addressed hash of receipt. identifier system `urn:labtrust:specimen`, value = same id |
| accession_ids[0] | Specimen.accessionIdentifier.value | First accession only |
| timestamps.received / timestamps.accepted | Specimen.receivedTime | Converted to FHIR dateTime (UTC ISO 8601); if only integer timestamp, also in extension `received-timestamp` |
| result_id | Observation.id, DiagnosticReport.id | One Observation and one DiagnosticReport per result receipt |
| panel_id | Observation.code.coding | system `urn:labtrust:test`, code and display = panel_id (or result_id if no panel_id) |
| device_ids[0] | Observation.extension | url `http://labtrust.org/fhir/StructureDefinition/device-identifier`, valueIdentifier (no Device resource in bundle) |
| reason_codes (CRIT / HIGH / LOW) | Observation.interpretation | CRIT → `v3-ObservationInterpretation` code `CR` (Critical); HIGH → `H`; LOW → `L` |
| timestamps.result_generated / released | Observation.issued, DiagnosticReport.effectiveDateTime | FHIR dateTime |
| decision | DiagnosticReport.status | RELEASED → `final`; HELD → `partial`; REJECTED → `entered-in-error`; BLOCKED → `registered` |
| (specimen link) | DiagnosticReport.specimen | When specimen receipts exist: reference to first Specimen in bundle (`#Specimen/<id>`). When none exist: Reference with only data-absent-reason extension (no Specimen resource). |

### Status assumptions (DiagnosticReport)

- **final**: Receipt decision = RELEASED (result released to care).
- **partial**: Receipt decision = HELD (result held, not yet final).
- **entered-in-error**: Receipt decision = REJECTED (specimen/result rejected).
- **registered**: Receipt decision = BLOCKED or other (registered, not yet final).

## Partner overlay hooks

- **partner_id**: Included in `Bundle.meta.tag` with system `http://labtrust.org/fhir/partner` and code = partner_id (from manifest or optional override).
- **policy_fingerprint**: Included in `Bundle.meta.extension` with url `http://labtrust.org/fhir/StructureDefinition/policy-fingerprint` and valueString = policy_fingerprint (from manifest).

## Validation

- **Structural checks**: Bundle has `resourceType` "Bundle", `type` "collection", and `entry[]` with `fullUrl` and `resource`. Each resource has `resourceType` and `id`. References that use `reference` resolve within the bundle (same-bundle references use `#ResourceType/id`). Specimen may be represented by a Reference with only the data-absent-reason extension (no `reference`), in which case no resolution is required. No resource `id` or fullUrl may contain "placeholder".
- **Determinism**: Same receipts directory (same file order and content) produces identical bundle JSON (canonical key ordering).
- **Export contract schema**: `policy/schemas/fhir_bundle_export.v0.1.schema.json` describes the minimal export contract (required keys, entry structure). This is not full FHIR profile validation.

## When specimen is missing (data-absent-reason)

When the receipts contain only result receipts (no specimen receipts), no Specimen resource is emitted. `Observation.specimen` and `DiagnosticReport.specimen` are set to a Reference object that contains **only** the HL7 data-absent-reason extension (no `reference` field, no Specimen in bundle):

```json
{
  "extension": [
    {
      "url": "http://hl7.org/fhir/StructureDefinition/data-absent-reason",
      "valueCode": "unknown"
    }
  ]
}
```

## When Observation value is missing (dataAbsentReason)

Receipts do not carry numeric lab values. The exporter omits `value[x]` entirely and sets `Observation.dataAbsentReason`:

```json
{
  "dataAbsentReason": {
    "coding": [
      {
        "system": "http://terminology.hl7.org/CodeSystem/data-absent-reason",
        "code": "unknown"
      }
    ]
  }
}
```

No placeholder text or placeholder IDs are used. Optional context may be added via `Observation.note` with explicit, non-placeholder wording if needed.

## Limitations

- **No numeric result value**: Receipts do not carry lab values; Observation uses dataAbsentReason as above. Real value/unit mapping would require extending the receipt or a separate value feed.
- **One Observation per result**: Each result receipt becomes one Observation and one DiagnosticReport. Multiple observations per report (e.g. panel with many analytes) would require multiple result receipts or a different mapping.
- **Specimen–result linking**: When specimen receipts exist, the first Specimen in the bundle is referenced by all Observations and DiagnosticReports. When none exist, specimen is represented via data-absent-reason extension only. Explicit specimen–result linking requires specimen_id on the result receipt.
- **No Device resource**: Device is represented as an Observation extension (identifier); no Device resource is emitted.
- **No full FHIR validation**: Only the minimal export contract and reference resolution are checked; no FHIR profile or terminology validation.

## End-to-end

1. Run: `labtrust reproduce --profile minimal --out runs/my_repro`
2. Export receipts: `labtrust export-receipts --run runs/my_repro/taska/logs/cond_0/episodes.jsonl --out runs/my_repro/taska/cond_0_export`
3. Export FHIR: `labtrust export-fhir --receipts runs/my_repro/taska/cond_0_export/EvidenceBundle.v0.1 --out runs/my_repro/taska/cond_0_fhir`

All tests (including export-receipts and export-fhir) should be green.
