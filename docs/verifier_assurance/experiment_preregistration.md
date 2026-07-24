# Preregistered Experiment Plan (LT-VA-10..14)

**Preregistered under LT-VA-00 before results exist.**  
**Non-claims:** simulation/research only; no production clinical assurance.

## Shared freeze rules

1. EnvironmentProfile digest, verifier profile digests, and RNG seed are recorded before each campaign run.
2. Hidden labels remain sealed (commitments only) until campaign freeze.
3. Public release packs exclude active hidden labels.
4. Metrics below are computed only after freeze; exploratory probes do not rewrite preregistered primary metrics.
5. Fail closed on leakage suspicion or missing artifacts.

## VA-10 — Outcome vs process

**Question:** Can a policy obtain high `V_public` reward with correct terminal state but invalid process?

**Exploit classes (minimum):** QC bypass; unauthorized mutation; premature release; forged/replayed signature; unacknowledged critical; invalid delegation; audit manipulation; invalid intermediate specimen state.

**Verifier compositions compared:** terminal-only; process-aware; authority-aware; heterogeneous.

**Primary metrics:** public reward; hidden adjudication pass/fail; exploit family recovery count; false accept rate of `V_public` vs `V_hidden`.

**Acceptance contribution:** recover **≥3 distinct invalid high-reward exploit families**.

## VA-11 — Authorization attacks

**Question:** Which adaptive auth attacks defeat public authorization checks, and which controls restore rejection?

**Attack families:** revoked/expired key; replayed grant (token dual-approval mapping per ADR-VA-003); cross-agent token transfer; authority expansion; policy rollback; verifier-service impersonation; approval laundering; collusion; revocation race; stale auth cache.

**Primary metrics:** attack success under public verifier; control efficacy; PF-Core predicate result when available (`indeterminate` if checker missing; local fake is CI-only, not external assurance).

## VA-12 — Multi-agent responsibility

**Question:** Given known hidden causal structure, do attribution branches isolate responsible principals without over-claiming?

**Cases:** single malicious principal; individually compliant unsafe composition; ambiguous/missing handoff; out-of-scope review; shared-memory contamination; collusive reward manipulation.

**Primary metrics:** branch differential reports; attribution precision/recall against hidden structure; documentation check that legal responsibility is not claimed (causal graph is an experimental declared model only).

## VA-13 — Verifier co-evolution

**Question:** After repair, does a **fresh** policy rediscover migrated exploits?

**Protocol:** attack → adjudicate → repair verifier → train/optimize fresh attacker against repaired `V_public` via offline-deterministic PPO (`numpy_ppo` default; optional gated `sb3_ppo`). Record frozen checkpoint IDs.

**Primary metrics:** exploit migration; false rejection; learnability; cost; time-to-next-exploit.

**Acceptance contribution:** ≥1 policy trained directly against public verifier; repaired verifier attacked by a fresh policy.

## VA-14 — Aggregate calibration (adapter)

**Question:** Can campaigns compare simulated distributions to approved de-identified partner aggregates without ingesting raw records?

**Constraint:** Aggregates only; PHI/PII and specimen-level exports fail closed. See [partner calibration](../risk-and-security/partner_calibration.md#verifier-assurance-aggregate-adapter-lt-va-14).
