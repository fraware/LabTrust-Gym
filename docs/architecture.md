# Architecture

LabTrust-Gym is structured as: core simulator (engine/), trust skeleton (policy/), runner (golden runner and adapter interface), and agents (outside env). Determinism: single RNG wrapper seeded from scenario; BLOCKED steps do not mutate world state except audit logging; hash chain break triggers forensic freeze.
