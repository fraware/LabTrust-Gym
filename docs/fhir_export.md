# FHIR R4 Export

See **[Evidence bundle verification](evidence_verification.md)** for verifying an EvidenceBundle.v0.1 (including integrity, schema, hashchain, and invariant trace) with `labtrust verify-bundle --bundle <dir>`.

The FHIR R4 exporter converts **Receipt.v0.1** (from an evidence bundle or receipts directory) into a minimal **FHIR R4 Bundle** (type = `collection`) containing Specimen, Observation(s), and DiagnosticReport. No external FHIR libraries are required; output is pure JSON with lightweight structural validation.

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
| specimen_id | Specimen.identifier | system `urn:labtrust:specimen`, value = specimen_id |
| accession_ids[0] | Specimen.accessionIdentifier.value | First accession only |
| timestamps.received / timestamps.accepted | Specimen.receivedTime | Converted to FHIR dateTime (UTC ISO 8601); if only integer timestamp, also in extension `received-timestamp` |
| result_id | Observation.id, DiagnosticReport.id | One Observation and one DiagnosticReport per result receipt |
| panel_id | Observation.code.coding | system `urn:labtrust:test`, code and display = panel_id (or result_id if no panel_id) |
| device_ids[0] | Observation.extension | url `http://labtrust.org/fhir/StructureDefinition/device-identifier`, valueIdentifier (no Device resource in bundle) |
| reason_codes (CRIT / HIGH / LOW) | Observation.interpretation | CRIT → `v3-ObservationInterpretation` code `CR` (Critical); HIGH → `H`; LOW → `L` |
| timestamps.result_generated / released | Observation.issued, DiagnosticReport.effectiveDateTime | FHIR dateTime |
| decision | DiagnosticReport.status | RELEASED → `final`; HELD → `partial`; REJECTED → `entered-in-error`; BLOCKED → `registered` |
| (specimen link) | DiagnosticReport.specimen | Reference to first Specimen in bundle (or placeholder if no specimen receipts) |

### Status assumptions (DiagnosticReport)

- **final**: Receipt decision = RELEASED (result released to care).
- **partial**: Receipt decision = HELD (result held, not yet final).
- **entered-in-error**: Receipt decision = REJECTED (specimen/result rejected).
- **registered**: Receipt decision = BLOCKED or other (registered, not yet final).

## Partner overlay hooks

- **partner_id**: Included in `Bundle.meta.tag` with system `http://labtrust.org/fhir/partner` and code = partner_id (from manifest or optional override).
- **policy_fingerprint**: Included in `Bundle.meta.extension` with url `http://labtrust.org/fhir/StructureDefinition/policy-fingerprint` and valueString = policy_fingerprint (from manifest).

## Validation

- **Structural checks**: Bundle has `resourceType` "Bundle", `type` "collection", and `entry[]` with `fullUrl` and `resource`. Each resource has `resourceType` and `id`. References (Specimen, Observation) resolve within the bundle (same-bundle references use `#ResourceType/id`).
- **Determinism**: Same receipts directory (same file order and content) produces identical bundle JSON (canonical key ordering).
- **Export contract schema**: `policy/schemas/fhir_bundle_export.v0.1.schema.json` describes the minimal export contract (required keys, entry structure). This is not full FHIR profile validation.

## Limitations

- **No numeric result value**: Receipts do not carry lab values; Observation uses a placeholder `valueString` ("result"). Real value/unit mapping would require extending the receipt or a separate value feed.
- **One Observation per result**: Each result receipt becomes one Observation and one DiagnosticReport. Multiple observations per report (e.g. panel with many analytes) would require multiple result receipts or a different mapping.
- **Specimen–result linking**: If result receipts do not carry specimen_id, the first Specimen in the bundle (or a single placeholder Specimen) is referenced by all DiagnosticReports. Explicit specimen–result linking requires specimen_id on the result receipt.
- **No Device resource**: Device is represented as an Observation extension (identifier); no Device resource is emitted.
- **No full FHIR validation**: Only the minimal export contract and reference resolution are checked; no FHIR profile or terminology validation.

## End-to-end

1. Run: `labtrust reproduce --profile minimal --out runs/my_repro`
2. Export receipts: `labtrust export-receipts --run runs/my_repro/taska/logs/cond_0/episodes.jsonl --out runs/my_repro/taska/cond_0_export`
3. Export FHIR: `labtrust export-fhir --receipts runs/my_repro/taska/cond_0_export/EvidenceBundle.v0.1 --out runs/my_repro/taska/cond_0_fhir`

All tests (including export-receipts and export-fhir) should be green.
