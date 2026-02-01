# Invariants

Invariants are defined in `policy/invariants/` (tokens, zones, critical results, **transport**). They specify:

- **Triggers**: which events or conditions invoke the check.
- **Logic**: assertions (e.g. token active, co-location, ACK present, transport temp in band, chain-of-custody).
- **Enforcement**: DENY_ACTION, BLOCK_ACTION, FORENSIC_FREEZE_LOG, etc.
- **Reason codes**: canonical code returned on violation.

The engine evaluates invariants at the appropriate hooks (e.g. pre_action_validate, post_action_log) and returns violations in the step result. The golden runner asserts expected violation tokens in scenario expectations.

## Transport and export in the golden suite

Transport invariants **INV-TRANSPORT-001** (temp in band) and **INV-COC-001** (chain-of-custody: dispatch must have receive or CHAIN_OF_CUSTODY_SIGN) are exercised by the golden suite:

- **GS-TRANSPORT-001**: Happy path dispatch → tick → sign → receive; no violations.
- **GS-TRANSPORT-002**: Temp excursion → BLOCKED with `TRANSPORT_TEMP_EXCURSION` and INV-TRANSPORT-001.
- **GS-COC-003**: Invalid/missing chain-of-custody → BLOCKED with `TRANSPORT_CHAIN_OF_CUSTODY_BROKEN` and INV-COC-001.

Export (receipts and FHIR) is covered by **GS-EXPORT-001**, which runs post-run hooks `EXPORT_RECEIPTS`, `VERIFY_BUNDLE`, `EXPORT_FHIR` after a normal episode and asserts output files exist and the evidence bundle manifest validates. See [Benchmarks](benchmarks.md#golden-suite-transport-and-export).
