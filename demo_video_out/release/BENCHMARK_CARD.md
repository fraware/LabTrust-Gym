# LabTrust-Gym Benchmark Card

## Scope

Blood Sciences lane: specimen reception, accessioning, pre-analytics, routine and STAT analytics, QC, critical result notification, and release. Multi-site transport (hub + acute) with consignments and chain-of-custody.

## Invariants and enforcement

- **Invariant registry** (v1.0): zone movement, co-location, restricted door, critical ack, stability, transport (INV-COC-001, INV-TRANSPORT-001), etc.
- **Enforcement**: optional throttle, kill_switch, freeze_zone, forensic_freeze via policy/enforcement.

## Tasks

| Task | Description | SLA |
|------|-------------|-----|
| throughput_sla | Throughput under SLA | 3600 s |
| stat_insertion | STAT insertion under load | 1800 s |
| qc_cascade | QC fail cascade | — |
| adversarial_disruption | Adversarial disruption | 3600 s |
| multi_site_stat | Multi-site STAT (transport latency) | 2400 s |

## Baselines

- **Scripted (ops + runner)**: deterministic policy; used in reproduce and package-release.
- **Adversary** (adversarial_disruption): scripted adversary agent.
- **PPO/MARL**: optional Stable-Baselines3; train-ppo / eval-ppo.
- **LLM mock**: optional LLM agent (deterministic backend).

## Known limitations and non-goals

- Golden suite: some scenarios (e.g. zone door alarm) may depend on enforcement or timing.
- Full FHIR validation: export is minimal structural; no terminology server.
- Transport: multi_site_stat scripted policy emits DISPATCH_TRANSPORT → TRANSPORT_TICK → CHAIN_OF_CUSTODY_SIGN → RECEIVE_TRANSPORT; transport is mandatory and audited.
