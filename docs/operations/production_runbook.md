# Production runbook

Concise runbook for teams taking the stack toward production. It covers configuration, key management, monitoring, rollback, and how the threat model applies.

## Configuration

- Set `LABTRUST_POLICY_DIR` to the policy directory (containing `emits/`, `schemas/`, and related files) when you use a custom policy tree instead of the package-bundled policy. Apply site-specific overrides with partner overlays (`--partner <id>` or `LABTRUST_PARTNER`) for critical thresholds, stability, and enforcement.
- Configure environment variables for API keys (for example `OPENAI_API_KEY` for live LLM), rate limits, and timeouts (for example `LABTRUST_LLM_TIMEOUT_S` and `global_rate_limit_max_wait_s` in scale config). See [Installation](../getting-started/installation.md) and [Scale and operational limits](../benchmarks/scale_operational_limits.md).
- Use `scale_configs.v0.1.yaml` and task defaults for scale and timing, and pass `--timing simulated` when device service times and turnaround time matter. For long or production-like runs, enable `--log` and `--checkpoint-every N`, and resume with `--resume-from <run_dir>`.

## Key management

- Store Ed25519 public keys for signed actions in `policy/keys/key_registry.v0.1.yaml` (and partner overlays). The registry supports lifecycle fields such as `status` (ACTIVE, REVOKED, EXPIRED) and optional `not_before_ts_s` / `not_after_ts_s`. Rotate keys by updating the registry and redeploying policy; the engine and `verify-bundle` read the registry at load and verify time.
- When `sign_bundle=True` and a key registry plus `get_private_key` callback are provided, the export signs the manifest and each receipt with Ed25519. Integrators own key custody and storage; the core export loads private keys only through the callback. See [Enforcement](../policy/enforcement.md) (Evidence bundle signing and verification).

## Monitoring

- Monitor invariant violations, blocked actions (including reason codes), security gate status (for example pack gate pass or fail), and, when using live LLM, latency and error rates. Useful run outputs include `results.json` metadata, `live_evaluation_metadata.json` (`wall_clock_s_*`, `llm_latency_ms_*`), `SECURITY/` attack results and coverage, and `pack_summary.csv` with `pack_gate.md`.
- Episode logs (JSONL), receipts, and hashchain proof support audit and verification. Point monitoring at run directories and evidence bundle locations defined in your deployment.

## Rollback

- Revert policy files (or a partner overlay) and redeploy, ensuring `LABTRUST_POLICY_DIR` or the package version points at the desired state. For code changes, roll back the deployed package version and re-run critical benchmarks to confirm behavior.
- Use checkpoint and resume (`--checkpoint-every`, `--resume-from`) so long runs can continue after interruption; integrators own persistence and backup of run directories.

## Threat model scope

The [Threat model](../architecture/threat_model.md) defines what the simulation enforces, including audit integrity, tokens, reason codes, and runtime control with signatures. Integrators own production hardening for key custody, network security, supply-chain integrity, and deployment topology. Simulation gates support assurance work alongside production controls. See [Operator's summary](operators_summary.md) and [Supply chain integrity](../risk-and-security/supply_chain_integrity.md) (optional integrity and TEE).

## See also

- [Threat model](../architecture/threat_model.md) — Trust boundary and out of scope.
- [Enforcement](../policy/enforcement.md) — Signing and verification of evidence bundles.
- [Scale and operational limits](../benchmarks/scale_operational_limits.md) — Rate limits, checkpointing, at-scale profiles.
- [Operator's summary](operators_summary.md) — What the sim proves and minimal production checklist.
- [Calibration guide](../policy/calibration_guide.md) — What to tune and how to validate.
