# Operator's summary

One-page summary for clinical and lab operators and non-developer stakeholders: what the simulation proves, what it does not, and a minimal production checklist.

## What the simulation proves

- **Deterministic benchmarks:** With the same seed and policy, the simulation produces reproducible outcomes; benchmarks (throughput, violations, blocks) are comparable across runs.
- **Invariants and controls:** The engine enforces RBAC, signed actions (ed25519), zone movement rules, critical-result acknowledgment, token lifecycle, and chain-of-custody. Violations and blocked actions are logged with reason codes.
- **Audit trail:** Append-only hash-chained audit log; no silent mutation after BLOCKED. Evidence bundles (receipts, manifest, hashchain proof) support verification and export (e.g. FHIR R4).
- **Security and coordination benchmarks:** Under defined risk injections (prompt injection, tool misuse, coordination-under-attack), the security attack suite and coordination security pack measure detection, containment, and throughput; results are recorded in pack summaries and risk register evidence.

## What it does not prove

- **Not a clinical validation:** Shipped critical thresholds and stability rules are reference defaults (e.g. RCPath 2017 style), not clinically validated. Sites must calibrate for their environment.
- **Not a replacement for production hardening:** Passing all sim tests and gates does not imply production safety. Deployment, key management, and operational security are the responsibility of integrators.
- **Supply-chain and runner out of scope:** The threat model assumes the runner and policy source are trusted. Compromised runner, malicious policy, and supply-chain attacks are out of scope; integrators must address these if required.

See [Threat model](../architecture/threat_model.md) for the full trust boundary and out-of-scope list.

## Minimal production checklist

Before taking the stack toward production:

1. **Calibrate thresholds** for your environment (critical result escalation, stability, equipment, enforcement). Use partner overlays or `LABTRUST_POLICY_DIR` with site-calibrated policy. See [Policy pack](../policy/policy_pack.md) and [Calibration guide](../policy/calibration_guide.md).
2. **Run red-team or penetration tests** in staging; use the security attack suite and coordination security pack as one input to assurance.
3. **Define production monitoring and rollback:** Monitor invariant violations, blocks, and security gate status; define how to revert policy or code and use checkpoint/resume for long runs.
4. **Key management:** Understand where the key registry lives, how signatures are used in evidence bundles, and how to rotate keys. See [Enforcement](../policy/enforcement.md) (signing) and [Production runbook](production_runbook.md).

See [Threat model](../architecture/threat_model.md) and [State of the art and limits](../reference/state_of_the_art_and_limits.md) (Deployment readiness) for more detail.

## See also

- [Threat model](../architecture/threat_model.md) — Trust boundary and out of scope.
- [Policy pack](../policy/policy_pack.md) — Production calibration (critical thresholds) and partner overlays.
- [Calibration guide](../policy/calibration_guide.md) — What to tune, where in policy, and how to validate.
- [Production runbook](production_runbook.md) — Config, key management, monitoring, rollback.
