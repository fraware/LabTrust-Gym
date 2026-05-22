# PCS demonstration limitations

LabTrust-Gym PCS v0.1 is intentionally scoped as a **research simulation** with the following boundaries.

- The workflow runs entirely inside the simulation environment without connections to hospital systems, laboratory information systems, or instruments.
- The demonstration makes no clinical safety, diagnostic, or regulatory claims.
- Assumptions embedded in exported bundles state that semantics apply only inside the simulation.
- Production of `TraceCertificate.v0` depends on CertifyEdge and external formal specifications.
- Signing and long-term storage depend on Provability Fabric and Scientific Memory.
- Hash stability requires fixed workflow timestamps in YAML and unchanged policy files between runs.

For the full multi-repository flow and disclaimer, see the [PCS operator runbook](examples/pcs_qc_release-operator.md).
