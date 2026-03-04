# Risk injections: extension contract

This document describes how to implement and register **risk injectors** for the coordination security pack and TaskH (coord_risk). For the risk register bundle and evidence, see [Risk register](risk_register.md).

## Naming conventions

- **INJ-*** (e.g. `INJ-COMMS-POISON-001`, `INJ-DOS-PLANNER-001`): Coordination/risk injectors defined in `policy/coordination/injections.v0.2.yaml`. Deterministic, policy-driven, and used for coord_risk and the coordination security pack. Prefer these for **active** fault injection in new specs.
- **inj_*** (e.g. `inj_prompt_injection`, `inj_tool_selection_noise`): Legacy or reserved IDs. Some have real implementations; five are reserved and implemented as **NoOpInjector** (passthrough) so specs that reference them do not fail.
- **none**: No injection (baseline/nominal cell in the coordination security pack).

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

## Injection ID reference (status and canonical use)

Single reference for which IDs are reserved (no-op) vs implemented (real injector) and what to use in new specs.

| Injection ID | Status | Canonical use |
|--------------|--------|---------------|
| `none` | Reserved (no-op) | No injection; baseline/nominal cell in coordination security pack. |
| `inj_collusion_handoff` | Reserved (no-op) | Legacy; prefer INJ-COLLUSION-001 for active faults. |
| `inj_untrusted_payload` | Reserved (no-op) | Legacy; use INJ-* from injections.v0.2.yaml when available. |
| `inj_stuck_state` | Reserved (no-op) | Legacy; use INJ-* when available. |
| `inj_jailbreak` | Reserved (no-op) | Legacy; use INJ-* when available. |
| `inj_prompt_injection` | Implemented (real injector) | PromptInjectionObsInjector; injects into scenario_note/specimen_note. |
| `inj_misparam_device` | Implemented (real injector) | MisparamDeviceInjector; perturbs device-related action args. |
| `inj_tool_selection_noise` | Implemented (real injector) | ToolSelectionNoiseInjector. |
| `inj_device_fail` | Implemented (real injector) | DeviceFailInjector. |
| `inj_msg_poison` | Implemented (real injector) | MsgPoisonInjector. |
| `inj_dos_flood` | Implemented (real injector) | DosFloodInjector. |
| `inj_memory_tamper` | Implemented (real injector) | MemoryTamperInjector. |
| `inj_poison_obs` | Implemented (real injector) | PoisonObsInjector. |
| INJ-* (e.g. `INJ-COMMS-POISON-001`, `INJ-DOS-PLANNER-001`) | Implemented (real injector) | **Use for new specs and coord_risk.** Defined in `policy/coordination/injections.v0.2.yaml`; deterministic, policy-driven. |

**Reserved IDs** (e.g. `inj_collusion_handoff`) are **no-op**: they do not perform any injection. Specs that reference them run without injection. Do not interpret results as evidence of "collusion" or other attack containment.

The five reserved no-op IDs above are in `RESERVED_NOOP_INJECTION_IDS` in `src/labtrust_gym/security/risk_injections.py`; they are registered as **NoOpInjector** so study specs and the risk register can reference them without failing. For **active** fault injection use **INJ-*** IDs from `policy/coordination/injections.v0.2.yaml`. Pack config supports **disallow_reserved_injections** so strict packs can forbid reserved (no-op) IDs.

## See also

- [Risk register](risk_register.md) — Bundle, evidence gaps, reserved IDs section
- [Coordination studies](../coordination/coordination_studies.md) — Study spec, injection matrix
- [Security attack suite](security_attack_suite.md) — Attack suite and coordination security pack
