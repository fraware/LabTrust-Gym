# Verifier Assurance Non-Claims

LabTrust-Gym verifier-assurance (LT-VA) work is **blood-sciences simulation and research only**.

It does **not**:

- Validate clinical laboratory software for production use
- Provide regulatory clearance, certification, or production clinical assurance
- Assign legal responsibility or liability via causal/attribution graphs (the causal graph is a declared experimental model only)
- Ingest or redistribute raw partner patient/specimen records
- Replace integrator-owned security audits or deployment hardening
- Claim that offline PPO / SB3 training against `V_public` transfers to production verifiers
- Claim PF-Core / OVK acceptance when the checker is unavailable (`indeterminate` only; local fake is for offline CI completeness, not external assurance)
- Claim that passing VA tests equals deployment readiness under distribution shift or live adversaries

## Fidelity limits (currency)

See EnvironmentProfile `known_fidelity_limits` and release pack fidelity metadata when present. Dual-oracle process boundaries, sealed IPC, and leakage tests reduce — but do not eliminate — the risk of optimization-induced verifier failure in deployment. Threat-model currency: [docs/architecture/threat_model.md](../architecture/threat_model.md) verifier-assurance extension.

Fail-closed rule: unknown schemas, missing artifacts, unavailable checkers, or leakage suspicion yield error or `indeterminate` — never acceptance presented as assurance.
