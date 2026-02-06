# Architecture diagrams

High-level visual overview of the main pipeline and of the HSL (Blood Sciences Lab) topology we model. Diagrams are in Mermaid; they render on GitHub and in MkDocs when using a Mermaid plugin (e.g. `mkdocs-mermaid2-plugin`). Otherwise copy the code into [Mermaid Live](https://mermaid.live) to view.

---

## 1. Main pipeline (high-level)

End-to-end flow from user/CLI through policy and tasks, environment, engine, and outputs.

```mermaid
flowchart TB
    subgraph inputs["Inputs"]
        CLI["CLI (quick-eval, run-benchmark, package-release, ...)"]
        Policy["Policy (policy/)\nzones, RBAC, tokens, invariants,\ncritical, catalogue, coordination"]
        Tasks["Tasks (TaskA–H)\nscenario, scale, metrics"]
        Baselines["Baselines\nscripted, adversary, LLM, MARL,\ncoordination methods"]
    end

    subgraph runner["Benchmark / study runner"]
        RunEp["run_episode / study_runner\nenv_factory, scripted_agents_map\ncoord_method, risk_injector"]
    end

    subgraph env_layer["Environment layer"]
        PZ["PettingZoo (Parallel / AEC)\nobservations, actions, rewards"]
    end

    subgraph engine["Engine (core_env)"]
        Reset["reset(initial_state, seed)"]
        Step["step(event)\nRBAC → signatures → domain logic"]
        Stores["Stores: audit_log, zones, specimens,\nqc, critical, queueing, devices,\ntransport, invariants, enforcement"]
        Step --> Stores
        Reset --> Stores
    end

    subgraph outputs["Outputs"]
        Contract["Step contract: status, emits,\nviolations, hashchain"]
        Log["Episode log (JSONL)\nresults.json (v0.2)"]
        Export["Export: receipts, EvidenceBundle,\nFHIR R4, ui-export"]
        Reports["Summarize, security suite,\nsafety case, official pack"]
    end

    CLI --> RunEp
    Policy --> RunEp
    Tasks --> RunEp
    Baselines --> RunEp
    RunEp --> PZ
    PZ --> Reset
    PZ --> Step
    Contract --> Log
    Log --> Export
    Log --> Reports
```

**Summary:** The CLI and config (policy, task, baseline) drive the benchmark runner. The runner builds an environment (optionally PettingZoo-wrapped) over the core engine. Each step goes through RBAC, signatures, and domain logic; the engine returns the step contract and appends to the audit log. Episode logs and results feed export (receipts, FHIR, UI bundle) and reporting (summarize, security suite, safety case, official pack).

---

## 2. HSL lab topology (modeled architecture)

Zone layout and specimen flow for the Blood Sciences Lab (HSL) at 60 Whitfield Street (automation hub). Two sites: **SITE_ACUTE** (STAT ingress) and **SITE_HUB** (routine lab). Arrows show permitted graph edges; the restricted branch requires a token. Devices are placed in the zones listed.

```mermaid
flowchart TB
    subgraph acute["SITE_ACUTE (STAT)"]
        Z_INGRESS["Z_INGRESS_DOCK\nIngress / Delivery"]
        Z_SRA["Z_SRA_RECEPTION\nSpecimen Reception"]
    end

    subgraph hub["SITE_HUB (routine lab)"]
        Z_ACC["Z_ACCESSIONING\nAccessioning"]
        Z_SORT["Z_SORTING_LANES\nSorting / Staging"]
        Z_PRE["Z_PREANALYTICS\nPre-analytics"]
        Z_CF["Z_CENTRIFUGE_BAY\nCentrifuge Bay"]
        Z_ALQ["Z_ALIQUOT_LABEL\nAliquot + Label"]
        Z_A["Z_ANALYZER_HALL_A\nAnalyzer Hall A"]
        Z_B["Z_ANALYZER_HALL_B\nAnalyzer Hall B"]
        Z_QC["Z_QC_SUPERVISOR\nQC Bench"]
        Z_FR["Z_COLD_FRIDGE"]
        Z_FZ["Z_COLD_FREEZER"]
    end

    subgraph restricted["Restricted (token required)"]
        Z_BIO["Z_RESTRICTED_BIOHAZARD\nBiohazard / High-control"]
        Z_WASTE["Z_WASTE_DISPOSAL\nWaste"]
    end

    Z_INGRESS -->|D_MAIN_INNER| Z_SRA
    Z_SRA --> Z_ACC
    Z_ACC --> Z_SORT
    Z_SORT --> Z_PRE
    Z_SORT --> Z_CF
    Z_PRE --> Z_CF
    Z_CF --> Z_ALQ
    Z_ALQ --> Z_A
    Z_ALQ --> Z_B
    Z_A --> Z_QC
    Z_B --> Z_QC
    Z_A --> Z_FR
    Z_B --> Z_FR
    Z_FR --> Z_FZ
    Z_SRA -->|D_RESTRICTED_AIRLOCK| Z_BIO
    Z_BIO -->|D_WASTE| Z_WASTE
```

**Device placement (from zone_layout_policy):**

| Zone | Devices |
|------|---------|
| Z_CENTRIFUGE_BAY | DEV_CENTRIFUGE_BANK_01 |
| Z_ALIQUOT_LABEL | DEV_ALIQUOTER_01 |
| Z_ANALYZER_HALL_A | DEV_CHEM_A_01, DEV_HAEM_01 |
| Z_ANALYZER_HALL_B | DEV_CHEM_B_01, DEV_COAG_01 |

**Transport:** Specimens can be dispatched from SITE_ACUTE to SITE_HUB (route ACUTE_TO_HUB; transport time and temp drift defined in `policy/sites/sites_policy.v0.1.yaml`). Chain-of-custody and temperature bands are enforced by the engine.

**Roles (RBAC):** Reception (SRA, accessioning), Runner (movement, pre-analytics, analytics), Pre-analytics, Analytics, QC, Supervisor, Biohazard (restricted area and waste). Restricted door D_RESTRICTED_AIRLOCK requires TOKEN_RESTRICTED_ENTRY and role ROLE_BIOHAZARD or ROLE_SUPERVISOR.

---

See [architecture.md](architecture.md) for component-level description and [repository_structure.md](repository_structure.md) for directory layout.
