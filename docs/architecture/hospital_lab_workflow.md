# Hospital lab workflow

This document gives two views of the hospital lab workflow modeled in LabTrust-Gym and how it differs under the **deterministic** and **LLM live** pipelines. Diagrams are Mermaid; they render on GitHub and in MkDocs with a Mermaid plugin. Otherwise paste the code into [Mermaid Live](https://mermaid.live).

---

## 1. High-level view

End-to-end specimen and agent flow: from reception to release, with roles and key decision points.

```mermaid
flowchart TB
    subgraph ingress["Ingress"]
        RECEP["Reception (SRA)"]
        SPEC["Specimens: ROUTINE / STAT"]
    end

    subgraph flow["Lab flow"]
        ACC["Accessioning"]
        SORT["Sorting / Staging"]
        PRE["Pre-analytics / Centrifuge"]
        ALQ["Aliquot + Label"]
        DEV["Analyzer (device run)"]
        QC["QC / Supervisor"]
    end

    subgraph egress["Egress"]
        RELEASE["Release result"]
    end

    RECEP --> SPEC
    SPEC --> ACC
    ACC --> SORT
    SORT --> PRE
    PRE --> ALQ
    ALQ --> DEV
    DEV --> QC
    QC --> RELEASE
```

**Agents (high-level):**

| Role | Id(s) | Responsibility |
|------|-------|-----------------|
| **Ops (scheduler)** | ops_0 | Decides which specimen to queue to which device (QUEUE_RUN). Can be scripted or LLM. |
| **Runner** | runner_0, runner_1 | Move between zones (MOVE), start runs on devices (START_RUN), deliver to QC. Scripted. |
| **QC / Supervisor** | qc_0, supervisor_0 | Gate and release results (RELEASE_RESULT). Scripted. |
| **Adversary** (optional) | adversary_0 | In adversarial_disruption: misroute, restricted door, replay. Deterministic policy. |
| **Insider** (optional) | adversary_insider_0 | In insider_key_misuse: RBAC deny, forged sig, token misuse. Deterministic phases. |

**SLA and metrics:** Specimens have a turnaround target (accept to release). Throughput, on-time rate, violations, and (for security tasks) detection latency and containment are recorded per episode.

---

## 2. Detailed view

Zones, actions, enforcement, and where the pipeline (deterministic vs LLM live) affects the loop.

```mermaid
flowchart TB
    subgraph agents["Agents"]
        OPS["ops_0\n(scheduler)"]
        RUN["runner_0, runner_1"]
        QC_AG["qc_0, supervisor_0"]
    end

    subgraph action_choice["Action choice"]
        SCRIPT["Scripted policy\n(fixed or seeded)"]
        LLM["LLM proposal\n(schema-valid)"]
        SHIELD["Shield\n(RBAC, allowed_actions)"]
    end

    subgraph engine["Engine (core_env)"]
        RBAC["RBAC"]
        SIG["Signatures\n(Ed25519, key lifecycle)"]
        DOMAIN["Domain logic\n(zones, queues, devices, QC)"]
        INV["Invariants\n(runtime checks)"]
        AUDIT["Audit log\n(hash chain)"]
    end

    subgraph state["State stores"]
        ZONES["Zones, doors\n(adjacency, restricted)"]
        SPEC_STORE["Specimens\n(status, panel, priority)"]
        QUEUES["Per-device queues"]
        DEVICES["Devices\n(IDLE / RUNNING)"]
        TOKENS["Tokens, critical\n(notify/ack)"]
    end

    OPS --> SCRIPT
    OPS --> LLM
    SCRIPT --> SHIELD
    LLM --> SHIELD
    SHIELD --> RBAC
    RBAC --> SIG
    SIG --> DOMAIN
    DOMAIN --> ZONES
    DOMAIN --> SPEC_STORE
    DOMAIN --> QUEUES
    DOMAIN --> DEVICES
    DOMAIN --> TOKENS
    DOMAIN --> INV
    DOMAIN --> AUDIT
    RUN --> SHIELD
    QC_AG --> SHIELD
```

**Key actions (emits):**

| Action | Typical agent | Effect |
|--------|----------------|--------|
| **TICK** | Any | Advance clock; door-open duration checks. |
| **MOVE** | Runner | Move agent between adjacent zones; restricted doors require token + role. |
| **QUEUE_RUN** | Ops | Assign specimen to device queue (specimen_id, device_id). |
| **START_RUN** | Runner | Start a run on an idle device (from queue); device goes RUNNING. |
| **RELEASE_RESULT** | QC/Supervisor | Release a result (throughput); may require critical ack. |
| **RELEASE_RESULT_OVERRIDE** | With token | Override path (e.g. drift token); audited. |

**Enforcement:** RBAC restricts actions by role. Signatures (when strict_signatures is on) bind actions to agent and key lifecycle (ACTIVE/REVOKED/EXPIRED). Invariants run after each step (zone, door, critical ack, etc.); violations and blocked reason codes are in the step contract. BLOCKED steps do not mutate world state except the audit log.

---

## 3. How the workflow differs: deterministic vs LLM live

The **same engine and domain logic** run in both pipelines. The difference is **who proposes actions** for the agents that can use an LLM (typically **ops_0**) and what happens around that proposal.

```mermaid
flowchart LR
    subgraph det["Deterministic pipeline"]
        D_IN["Same: task, seed,\nzones, devices, RBAC"]
        D_OP["Scripted ops_0\n(fixed or seeded policy)"]
        D_ENG["Engine\n(step, audit, invariants)"]
        D_OUT["Same: results schema\nReproducible: same seed => same metrics"]
        D_IN --> D_OP
        D_OP --> D_ENG
        D_ENG --> D_OUT
    end

    subgraph live["LLM live pipeline"]
        L_IN["Same: task, seed,\nzones, devices, RBAC"]
        L_LLM["Live LLM\n(OpenAI / Anthropic / Ollama)"]
        L_SHIELD["Shield: validate proposal\nallowed_actions, RBAC"]
        L_ENG["Engine\n(step, audit, invariants)"]
        L_OUT["Same: results schema\n+ pipeline_mode, llm_backend_id\n+ metadata (latency, tokens, cost)\nNon-deterministic"]
        L_IN --> L_LLM
        L_LLM --> L_SHIELD
        L_SHIELD --> L_ENG
        L_ENG --> L_OUT
    end
```

| Aspect | Deterministic | LLM live |
|--------|----------------|----------|
| **Action proposal (e.g. ops_0)** | Scripted policy (or deterministic LLM backend with fixtures). No network. | Live LLM backend: state + allowed_actions sent to provider; response must match ActionProposal schema. |
| **Validation** | Same: shield checks allowed_actions, RBAC. Invalid or disallowed action → BLOCKED / NOOP. | Same shield. In addition: schema validation; invalid JSON or out-of-schema → NOOP with RC_LLM_INVALID_OUTPUT. Timeout/refusal/429 → NOOP with reason code. |
| **Network** | Forbidden. Any attempt to call an API fails fast. | Allowed only when `--pipeline-mode llm_live` and `--allow-network` (or LABTRUST_ALLOW_NETWORK=1). |
| **Reproducibility** | Same seed and task yield identical metrics and episode log. | Non-deterministic; same seed can yield different throughput/violations. |
| **Outputs** | results.json (v0.2), episode log, receipts. No LLM metadata. | Same results schema plus pipeline_mode, llm_backend_id, llm_model_id; metadata has latency, tokens, error_rate, optional cost. TRANSPARENCY_LOG/llm_live.json and live_evaluation_metadata.json for packs. |
| **Use case** | CI, baseline regression, reproducibility, release verification. | Live evaluation, provider comparison, transparency and cost attribution. |

**Summary:** The hospital lab workflow (zones, devices, specimens, QUEUE_RUN → START_RUN → RELEASE_RESULT, RBAC, signatures, invariants) is **identical** in both pipelines. Only the **source of the action proposal** for LLM-capable agents (and thus network and reproducibility) differs. Results and episode logs share the same schema so you can compare scripted vs LLM in one table via summarize-results.

---

## See also

- [Architecture](architecture.md) — Core simulator, policy, baselines, benchmarks.
- [Architecture diagrams](diagrams.md) — Main pipeline and HSL lab topology (zones, devices).
- [Benchmarks](../benchmarks/benchmarks.md) — Task definitions (throughput_sla, stat_insertion, adversarial_disruption, etc.).
- [Live LLM](../agents/llm_live.md) — Pipeline modes, guardrails, and pre-flight checklist.
