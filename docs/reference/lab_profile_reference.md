# Lab profile reference

A lab profile is a YAML file that defines a single source of truth for partner overlay, paths, and provider IDs when running LabTrust-Gym. Use `labtrust --profile <profile_id> <command> ...` to apply a profile.

## File location and naming

- **Path:** `policy/lab_profiles/<profile_id>.v0.1.yaml`
- **Example:** `policy/lab_profiles/hospital_lab.v0.1.yaml` for profile_id `hospital_lab`
- The CLI loads the profile when `--profile <profile_id>` is set; the file name must be `<profile_id>.v0.1.yaml`.

## Top-level fields

All fields are optional. When a field is null or omitted, the default behavior is used (repo defaults or built-in provider).

| Field | Type | Default | Meaning |
|-------|------|---------|--------|
| `version` | string | - | Schema version (e.g. `"0.1"`). Reserved for future use. |
| `profile_id` | string | - | Identifier matching the profile file name (e.g. `hospital_lab`). |
| `description` | string | - | Human-readable description of the lab profile. |
| `partner_id` | string \| null | null | Partner overlay ID. When set, applied to validate-policy, run-benchmark, run-security-suite, run-official-pack, and other commands that support `--partner`. |
| `benchmark_pack_path` | string \| null | null | Path to the benchmark pack YAML, relative to policy root. When null, use `policy/official/benchmark_pack.v0.1.yaml` (and partner overlay if applicable). See [Extension development](../agents/extension_development.md) for provider contracts and path overrides. |
| `security_suite_path` | string \| null | null | Path to the security attack suite YAML, relative to policy root. When null, use `policy/golden/security_attack_suite.v0.1.yaml` (and partner overlay if applicable). |
| `safety_claims_path` | string \| null | null | Path to the safety case claims YAML, relative to policy root. When null, use `policy/safety_case/claims.v0.1.yaml`. |
| `coordination_study_spec_path` | string \| null | null | Path to the coordination study spec YAML, relative to policy root. When null, use the default path used by run-coordination-study. |
| `security_suite_provider_id` | string \| null | null | Registered security suite provider ID. When set, run-security-suite uses this provider. When null, use the default provider. |
| `safety_case_provider_id` | string \| null | null | Registered safety case provider ID. When set, safety-case command uses this provider. When null, use the default provider. |
| `metrics_aggregator_id` | string \| null | null | Registered metrics aggregator ID. When set, run-benchmark and run-official-pack use this aggregator for episode metrics. When null, use the default aggregator. |
| `domain_id` | string \| null | null | Domain adapter ID. When set, commands that use the domain registry (e.g. scenario runs) resolve the adapter via `get_domain_adapter_factory(domain_id)`. Default domain is `hospital_lab`. See [Extension development](../agents/extension_development.md). |
| `extension_packages` | array of strings | [] | List of Python package names to import after applying the profile so that their entry_points (and any registration at import time) run. Optional; failed imports are ignored. |

## Path semantics

- Path fields (`benchmark_pack_path`, `security_suite_path`, `safety_claims_path`, `coordination_study_spec_path`) are **relative to the policy root** (the directory such that `policy_root / "policy"` is the policy directory). Absolute paths are supported where the value starts with `/` (Unix) or is a Windows absolute path.
- When a path field is null, the core uses its default path under the policy directory. Default paths are centralized in `labtrust_gym.config.get_effective_path()` (and in the CLI when applying a profile).

## Provider IDs

Provider IDs must refer to a registered provider. See [Extension development](../agents/extension_development.md) for how to register security suite, safety case, and metrics aggregator providers. If a profile references an unknown provider ID, the CLI may validate at startup and fail with a clear error (see [Extension development](../agents/extension_development.md)).

## Validation

When `policy/lab_profiles/lab_profile.v0.1.schema.json` exists and the `jsonschema` package is available, the CLI validates loaded profile YAML against that schema. If validation fails, the profile is treated as invalid (not loaded). See the schema file for the allowed structure.

## See also

- [Extension development](../agents/extension_development.md) for provider contracts and entry_points
- [Extension development](../agents/extension_development.md) for path overrides and provider contracts
