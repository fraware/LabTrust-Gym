# Injector get_metrics() contract (3a.3)

For `compute_episode_metrics` to populate `out["sec"]` consistently, every risk injector used in the coordination security pack (or any study that reports `sec.*`) must implement `get_metrics()` and return a dict that includes the following keys (values may be `None` or `False` for reserved/no-op injectors):

- **attack_success** (bool): Whether the injection led to an accepted mutating action.
- **first_application_step** (int | None): First step index at which the injection was applied.
- **first_detection_step** (int | None): First step at which the attack was detected.
- **first_containment_step** (int | None): First step at which the attack was contained.

Reserved/no-op injectors (e.g. `none`) may return zeros or a `reserved: True` flag; `sec.attack_success_rate` may be null or 0 by design for those cells.
