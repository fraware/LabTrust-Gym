# PCS demonstration limitations

LabTrust-Gym PCS v0.1 is intentionally scoped as a **research simulation**:

- No connection to real hospital systems, LIS, or instruments.
- No clinical safety, diagnostic, or regulatory claims.
- Assumptions in exported bundles state that semantics are simulation-only.
- `TraceCertificate.v0` production depends on CertifyEdge and external formal specs.
- Signing and long-term storage depend on Provability Fabric and Scientific Memory.
- Hash stability requires fixed workflow timestamps in YAML and unchanged policy files between runs.

For the full multi-repo flow and disclaimer, see [examples/pcs_qc_release/RUNBOOK.md](../examples/pcs_qc_release/RUNBOOK.md).
