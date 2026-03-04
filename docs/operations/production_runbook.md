# Production runbook

Concise runbook for teams taking the stack toward production: configuration, key management, monitoring, rollback, and where the threat model applies.

## Configuration

- **Policy root:** Set `LABTRUST_POLICY_DIR` to the policy directory (containing `emits/`, `schemas/`, etc.) when not using the package-bundled policy. Use partner overlays (`--partner <id>` or `LABTRUST_PARTNER`) for site-specific overrides (critical thresholds, stability, enforcement).
- **Environment variables:** API keys (e.g. `OPENAI_API_KEY`) for live LLM; rate limits and timeouts (e.g. `LABTRUST_LLM_TIMEOUT_S`, scale_config `global_rate_limit_max_wait_s`). See [Installation](../getting-started/installation.md) and [Scale and operational limits](../benchmarks/scale_operational_limits.md).
- **Scale and timing:** `scale_configs.v0.1.yaml` and task/spec defaults; use `--timing simulated` when device service times and TAT matter. For long or production-like runs, use `--log` and `--checkpoint-every N`; resume with `--resume-from <run_dir>`.

## Key management

- **Key registry:** Ed25519 public keys for signed actions live in `policy/keys/key_registry.v0.1.yaml` (and partner overlays). Key lifecycle: optional `status` (ACTIVE, REVOKED, EXPIRED), optional `not_before_ts_s` / `not_after_ts_s`. Rotation: update the registry and redeploy policy; the engine and verify-bundle use the registry at load/verify time.
- **Evidence bundle signing:** When `sign_bundle=True` and a key registry plus `get_private_key` callback are provided, the manifest and each receipt are signed with Ed25519. Key custody and storage are the integrator’s responsibility; the core export does not read keys from disk. See [Enforcement](../policy/enforcement.md) (Evidence bundle signing and verification).

## Monitoring

- **What to monitor:** Invariant violations, blocked actions (and reason codes), security gate status (e.g. pack gate pass/fail), and—when using live LLM—LLM latency and error rates. Use run outputs: `results.json` metadata, `live_evaluation_metadata.json` (wall_clock_s_*, llm_latency_ms_*), SECURITY/ attack_results and coverage, pack_summary.csv and pack_gate.md.
- **Logs and evidence:** Episode logs (JSONL), receipts, and hashchain proof support audit and verification. Point monitoring at run directories and evidence bundle locations as defined in your deployment.

## Rollback

- **Policy or code revert:** Revert policy files (or partner overlay) and redeploy; ensure `LABTRUST_POLICY_DIR` or package version points at the desired state. For code, roll back the deployed package version and re-run critical benchmarks to confirm.
- **Long runs:** Use checkpoint and resume (`--checkpoint-every`, `--resume-from`) so runs can be resumed after interruption; persistence and backup of run dirs are the integrator’s responsibility.

## Threat model scope

The [Threat model](../architecture/threat_model.md) defines what the simulation enforces (audit integrity, tokens, reason codes, runtime control with signatures, etc.). Production hardening—key custody, network security, supply-chain integrity, and deployment topology—is the **integrator’s responsibility**. Passing all sim tests and gates does not imply production safety. See [Operator's summary](operators_summary.md) and [Supply chain integrity](../risk-and-security/supply_chain_integrity.md) (optional integrity and TEE).

## See also

- [Threat model](../architecture/threat_model.md) — Trust boundary and out of scope.
- [Enforcement](../policy/enforcement.md) — Signing and verification of evidence bundles.
- [Scale and operational limits](../benchmarks/scale_operational_limits.md) — Rate limits, checkpointing, at-scale profiles.
- [Operator's summary](operators_summary.md) — What the sim proves and minimal production checklist.
- [Calibration guide](../policy/calibration_guide.md) — What to tune and how to validate.
