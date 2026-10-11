# Presentation and demonstration guide

LabTrust-Gym is a research simulator and benchmark for multi-agent laboratory workflows. Demonstrations must clearly distinguish simulated runs, policy checks, and software validation from external clinical evaluation or deployment authorization.

## Prepare the demonstration

Start with the [quick demos](getting-started/quick_demos.md) and the [demo readiness guide](getting-started/demo_readiness.md). Use the [architecture overview](architecture/index.md) to explain the agent roles, workflow transitions, and observations; use the [trust verification guide](risk-and-security/trust_verification.md) to describe evidence checks.

## Present results

Reference the [official benchmark pack](benchmarks/official_benchmark_pack.md), the [determinism contract](benchmarks/determinism_contract.md), and the [scientific credibility statement](benchmarks/scientific_credibility.md). Identify the executed scenario, seed, policies, data provenance, checked properties, and any applicable coverage gaps. Describe independently reviewed claims only where signed reviews have been recorded in the [review registry and protocol](reviews/README.md).

## Suggested presentation sequence

1. Scope and limitations of the simulator
2. Scenario setup and agent execution
3. Policy decision, observations, and resulting artifacts
4. Reproducibility and verification checks
5. Coverage gaps, evidence limitations, and next evaluation steps

The [release runbook](benchmarks/release_runbook.md) and [reviewer runbook](operations/reviewer_runbook.md) provide the procedures and evidence needed for a reproducible presentation.
