# Operator's summary

One-page summary for clinical and lab operators and non-developer stakeholders. It states what the simulation proves, where assurance stops, and gives a minimal production checklist.

## What the simulation proves

- **Deterministic benchmarks:** With the same seed and policy, the simulation produces reproducible outcomes; benchmarks (throughput, violations, blocks) are comparable across runs.
- **Invariants and controls:** The engine enforces RBAC, signed actions (ed25519), zone movement rules, critical-result acknowledgment, token lifecycle, and chain-of-custody. Violations and blocked actions are logged with reason codes.
- **Audit trail:** Append-only hash-chained audit log; no silent mutation after BLOCKED. Evidence bundles (receipts, manifest, hashchain proof) support verification and export (e.g. FHIR R4).
- **Security and coordination benchmarks:** Under defined risk injections (prompt injection, tool misuse, coordination-under-attack), the security attack suite and coordination security pack measure detection, containment, and throughput; results are recorded in pack summaries and risk register evidence.

## Scope limits

- **Clinical validation is separate.** Shipped critical thresholds and stability rules are reference defaults (for example RCPath 2017 style). Sites must calibrate them for their environment before clinical use.
- **Production hardening stays with integrators.** Passing all simulation tests and gates supports assurance work; deployment, key management, and operational security remain integrator responsibilities.
- **Runner and policy are trusted in simulation.** The threat model treats the runner and policy source as trusted. Integrators who need assurance against compromised runners, malicious policy, or supply-chain attacks should add integrity verification and operational controls described in [Supply chain integrity](../risk-and-security/supply_chain_integrity.md).

See [Threat model](../architecture/threat_model.md) for the full trust boundary and out-of-scope list.

## Minimal production checklist

Before taking the stack toward production:

1. **Calibrate thresholds** for your environment (critical result escalation, stability, equipment, enforcement). Use partner overlays or `LABTRUST_POLICY_DIR` with site-calibrated policy. See [Policy pack](../policy/policy_pack.md) and [Calibration guide](../policy/calibration_guide.md).
2. **Run red-team or penetration tests** in staging; use the security attack suite and coordination security pack as one input to assurance.
3. **Define production monitoring and rollback.** Monitor invariant violations, blocks, and security gate status, and document how to revert policy or code and how to use checkpoint and resume for long runs.
4. **Plan key management.** Learn where the key registry lives, how signatures appear in evidence bundles, and how to rotate keys. See [Enforcement](../policy/enforcement.md) (signing) and [Production runbook](production_runbook.md).

See [Threat model](../architecture/threat_model.md) and [State of the art and limits](../reference/state_of_the_art_and_limits.md) (Deployment readiness) for more detail.

## See also

- [Threat model](../architecture/threat_model.md) — Trust boundary and out of scope.
- [Policy pack](../policy/policy_pack.md) — Production calibration (critical thresholds) and partner overlays.
- [Calibration guide](../policy/calibration_guide.md) — What to tune, where in policy, and how to validate.
- [Production runbook](production_runbook.md) — Config, key management, monitoring, rollback.
