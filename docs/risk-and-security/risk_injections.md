# Risk injections: extension contract

This document describes how to implement and register **risk injectors** for the coordination security pack and TaskH (coord_risk). For the risk register bundle and evidence, see [Risk register](risk_register.md).

## Implementing a RiskInjector

1. **Subclass** `labtrust_gym.security.risk_injections.RiskInjector` and pass an `InjectionConfig` to `super().__init__(config)`.

2. **Override** the mutation hooks as needed:
   - **`_mutate_obs_impl(self, obs: dict) -> tuple[dict, dict | None]`** — Return (possibly mutated observation dict, optional audit entry). Default: no-op (return obs, None).
   - **`mutate_messages(self, messages: list) -> tuple[list, dict | None]`** — Return (possibly mutated messages, optional audit entry). Default: no-op.
   - **`_mutate_actions_impl(self, action_dict: dict) -> tuple[dict, list[dict]]`** — Return (possibly mutated action_dict, list of audit entries). Default: no-op.

3. **Determinism:** Use `self._rng` (a `random.Random` instance seeded from episode seed + config.seed_offset) for any randomness. Do not use module-level or global RNG.

4. **Audit:** When you mutate, append an audit entry via `_audit_entry(EMIT_INJECTION_APPLIED, self.injection_id, self._step, payload)` and return it so the runner can record it. Optionally override `observe_step(step_outputs)` to emit SECURITY_INJECTION_DETECTED / SECURITY_INJECTION_CONTAINED when the system detects or contains the attack.

5. **Registration:** Add your class to `INJECTION_REGISTRY` in `src/labtrust_gym/security/risk_injections.py`:
   - `INJECTION_REGISTRY["YOUR_INJECTION_ID"] = YourInjectorClass`
   - The factory `make_injector(injection_id, intensity=0.2, seed_offset=0, target=None, **kwargs)` instantiates the registered class with an `InjectionConfig`.

6. **Policy:** Add the injection ID to `policy/coordination/injections.v0.2.yaml` and, if used in the coordination security pack gate, to `policy/coordination/coordination_security_pack_gate.v0.1.yaml` with a rule type (e.g. `attack_success_rate_zero`, `violations_within_delta`). See `src/labtrust_gym/policy/gate_eval.py` and [Risk register](risk_register.md) for supported rule types.

## Reserved no-op IDs (out of scope for this release)

The following IDs are **reserved** and registered as **NoOpInjector** (passthrough; no observation or action mutation) so that study specs and the risk register can reference them without failing. For **active** fault injection use **INJ-*** IDs from `policy/coordination/injections.v0.2.yaml`.

| ID | Notes |
|----|--------|
| `none` | No-op baseline for coordination security pack (nominal cell). |
| `inj_tool_selection_noise` | Reserved; no-op in this release. |
| `inj_prompt_injection` | Reserved; no-op in this release. |
| `inj_dos_flood` | Reserved; no-op in this release. |
| `inj_collusion_handoff` | Reserved; no-op in this release. |
| `inj_untrusted_payload` | Reserved; no-op in this release. |
| `inj_memory_tamper` | Reserved; no-op in this release. |
| `inj_stuck_state` | Reserved; no-op in this release. |
| `inj_jailbreak` | Reserved; no-op in this release. |
| `inj_misparam_device` | Reserved; no-op in this release. |

The reserved list (10 IDs above) is in `RESERVED_NOOP_INJECTION_IDS`. **Implemented as real injectors:** `inj_device_fail` (DeviceFailInjector), `inj_msg_poison` (MsgPoisonInjector), `inj_poison_obs` (PoisonObsInjector: observation poisoning with probability intensity). Pack config supports **disallow_reserved_injections**. Implementing full injectors for the remaining reserved IDs is future work.

## See also

- [Risk register](risk_register.md) — Bundle, evidence gaps, reserved IDs section
- [Coordination studies](../coordination/coordination_studies.md) — Study spec, injection matrix
- [Security attack suite](security_attack_suite.md) — Attack suite and coordination security pack
