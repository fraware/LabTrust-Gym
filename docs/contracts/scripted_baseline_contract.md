# Scripted baseline policy contract

Scripted ops and runner agents can be configured via YAML policy files. No file or empty file => in-code defaults.

## Paths

- **Scripted ops:** `policy/scripted/scripted_ops_policy.v0.1.yaml`
- **Scripted runner:** `policy/scripted/scripted_runner_policy.v0.1.yaml`
- **Schemas:** `policy/schemas/scripted_ops_policy.v0.1.schema.json`, `policy/schemas/scripted_runner_policy.v0.1.schema.json`

## Scripted ops policy (v0.1)

| Key | Type | Description |
|-----|------|-------------|
| `version` | string | e.g. `"0.1"`. |
| `device_ids` | list[str] | Device IDs in order (index used for alternate_devices). |
| `alternate_devices` | map (int or str key -> list[int]) | Device index -> list of alternate device indices. |
| `priority_order` | list[str] | e.g. `["STAT", "URGENT", "ROUTINE"]`. |
| `edf_deadline_field` | string | Work item field for EDF (e.g. `deadline_s`). |
| `door_tick_threshold_s` | number | Seconds after which scripted ops emits TICK for restricted door. |
| `max_queue_len` | int | Max queue length per device; hold when full. |
| `request_override_if_configured` | bool | Use override token when stability/temp borderline. |

Missing keys leave in-code defaults unchanged.

## Scripted runner policy (v0.1)

| Key | Type | Description |
|-----|------|-------------|
| `version` | string | e.g. `"0.1"`. |
| `zone_ids` | list[str] | Zone IDs (order matches env my_zone_idx). |
| `workflow_zone_order` | list[str] | Zone order for workflow goal. |
| `restricted_zone_id` | string | Restricted zone (e.g. biohazard). |
| `restricted_door_id` | string | Door ID for restricted zone. |
| `door_tick_threshold_s` | number | Seconds after which runner emits TICK for door. |

Missing keys leave in-code defaults unchanged.

## Loader

- `labtrust_gym.policy.scripted.load_scripted_ops_policy(policy_path_arg=None, repo_root=None, validate=True)` returns a dict; empty if path is None or file missing.
- `labtrust_gym.policy.scripted.load_scripted_runner_policy(...)` same.

Agents accept `policy_path` and `policy_dict` in `__init__`; when `policy_dict` is None, the loader is called (default repo path or given path). See [Scripted baselines](../agents/scripted_baselines.md).
