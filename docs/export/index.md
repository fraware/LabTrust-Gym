# Export and verification

Export formats and verification commands.

## Export

| Document | Description |
|----------|-------------|
| [FHIR R4 export](fhir_export.md) | Valid HL7 FHIR R4 Bundle (data-absent-reason, no placeholder IDs). |
| [UI data contract](../contracts/ui_data_contract.md) | ui-export bundle: index, events, receipts_index, reason_codes; when run has coordination data, **coordination_artifacts** (SOTA leaderboards, method-class comparison, **coordination/graphs/** HTML charts). See [Frontend handoff](../reference/frontend_handoff_ui_bundle.md) for integration. |

## Verification

Release verification is documented in [Trust verification](../risk-and-security/trust_verification.md) and [CI](../operations/ci.md). Use `verify-bundle` for a single EvidenceBundle and `verify-release` for a full release directory.
