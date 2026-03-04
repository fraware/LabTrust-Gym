"""
Tests for modularity: registries (tasks, coordination, invariant handlers, providers, pack loader)
and that profile provider IDs are passed through.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

# Unique prefix to avoid clashing with built-in names
_MOD_PREFIX = "_modularity_test_"


def _stub_task_name() -> str:
    return f"{_MOD_PREFIX}task"


def _stub_coord_id() -> str:
    return f"{_MOD_PREFIX}coord"


def _stub_invariant_type() -> str:
    return "test_modularity_stub"


def _stub_invariant_check() -> str:
    return "stub"


def _stub_security_provider_id() -> str:
    return f"{_MOD_PREFIX}security"


def _stub_safety_provider_id() -> str:
    return f"{_MOD_PREFIX}safety"


def _stub_metrics_aggregator_id() -> str:
    return f"{_MOD_PREFIX}metrics"


def _stub_pack_loader_id() -> str:
    return f"{_MOD_PREFIX}pack_loader"


# ----- Tasks -----


def test_register_task_and_get_task() -> None:
    """Register a minimal task and resolve it via get_task."""
    from labtrust_gym.benchmarks.tasks import (
        BenchmarkTask,
        get_task,
        list_tasks,
        register_task,
    )

    class StubTask(BenchmarkTask):
        def __init__(self) -> None:
            super().__init__(
                name=_stub_task_name(),
                max_steps=10,
                scripted_agents=[],
                reward_config={},
            )

        def get_initial_state(
            self,
            seed: int,
            calibration: dict[str, Any] | None = None,
            policy_root: Path | None = None,
        ) -> dict[str, Any]:
            return {"seed": seed, "specimens": []}

    name = _stub_task_name()
    register_task(name, StubTask)
    try:
        assert name in list_tasks()
        task = get_task(name)
        assert isinstance(task, StubTask)
        assert task.name == name
    finally:
        # Unregister to avoid affecting other tests
        from labtrust_gym.benchmarks.tasks import _TASK_REGISTRY

        _TASK_REGISTRY.pop(name, None)


# ----- Coordination -----


def test_register_coordination_method_and_make() -> None:
    """Register a coordination factory and resolve via make_coordination_method."""
    from labtrust_gym.baselines.coordination.interface import CoordinationMethod
    from labtrust_gym.baselines.coordination.registry import (
        list_coordination_methods,
        make_coordination_method,
        register_coordination_method,
    )

    class StubCoordinationMethod(CoordinationMethod):
        @property
        def method_id(self) -> str:
            return mid

        def reset(self, seed: int, policy: dict[str, Any], scale_config: dict[str, Any] | None) -> None:
            pass

        def propose_actions(
            self, obs: dict[str, Any], infos: dict[str, dict[str, Any]], t: int
        ) -> dict[str, dict[str, Any]]:
            return {}

    mid = _stub_coord_id()

    def _factory(
        policy: dict[str, Any],
        repo_root: Path | None,
        scale_config: dict[str, Any] | None,
        params: dict[str, Any],
    ) -> CoordinationMethod:
        return StubCoordinationMethod()

    register_coordination_method(mid, _factory)
    try:
        assert mid in list_coordination_methods()
        method = make_coordination_method(mid, {}, None, None, {})
        assert isinstance(method, StubCoordinationMethod)
    finally:
        from labtrust_gym.baselines.coordination.registry import _COORDINATION_FACTORIES

        _COORDINATION_FACTORIES.pop(mid, None)


# ----- Invariant handlers -----


def test_register_invariant_handler_appears_in_registry() -> None:
    """Register an invariant handler and assert it is in the runtime registry."""
    from labtrust_gym.engine import invariants_runtime

    def _handler(
        env: Any, event: dict[str, Any], params: dict[str, Any]
    ) -> tuple[bool, str | None, dict[str, Any] | None] | None:
        return (True, None, None)

    logic_type = _stub_invariant_type()
    check_name = _stub_invariant_check()
    invariants_runtime.register_invariant_handler(logic_type, check_name, _handler)
    try:
        assert (logic_type, check_name) in invariants_runtime._TEMPLATE_HANDLERS
        assert invariants_runtime._TEMPLATE_HANDLERS[(logic_type, check_name)] is _handler
    finally:
        invariants_runtime._TEMPLATE_HANDLERS.pop((logic_type, check_name), None)


# ----- Security suite provider -----


def test_register_and_get_security_suite_provider() -> None:
    """Register a security suite provider stub and get it."""
    from labtrust_gym.benchmarks.security_runner import (
        get_security_suite_provider,
        register_security_suite_provider,
    )

    stub = object()
    pid = _stub_security_provider_id()
    register_security_suite_provider(pid, stub)
    try:
        got = get_security_suite_provider(pid)
        assert got is stub
    finally:
        from labtrust_gym.benchmarks.security_runner import _SECURITY_SUITE_PROVIDERS

        _SECURITY_SUITE_PROVIDERS.pop(pid, None)


# ----- Safety case provider -----


def test_register_and_get_safety_case_provider() -> None:
    """Register a safety case provider stub and get it."""
    from labtrust_gym.security.safety_case import (
        get_safety_case_provider,
        register_safety_case_provider,
    )

    stub = object()
    pid = _stub_safety_provider_id()
    register_safety_case_provider(pid, stub)
    try:
        got = get_safety_case_provider(pid)
        assert got is stub
    finally:
        from labtrust_gym.security.safety_case import _SAFETY_CASE_PROVIDERS

        _SAFETY_CASE_PROVIDERS.pop(pid, None)


# ----- Metrics aggregator -----


def test_register_and_get_metrics_aggregator() -> None:
    """Register a metrics aggregator stub and get it."""
    from labtrust_gym.benchmarks.metrics import (
        get_metrics_aggregator,
        register_metrics_aggregator,
    )

    def _stub_aggregator(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return {"stub": True}

    pid = _stub_metrics_aggregator_id()
    register_metrics_aggregator(pid, _stub_aggregator)
    try:
        got = get_metrics_aggregator(pid)
        assert got is _stub_aggregator
    finally:
        from labtrust_gym.benchmarks.metrics import _METRICS_AGGREGATORS

        _METRICS_AGGREGATORS.pop(pid, None)


# ----- Benchmark pack loader -----


def test_register_and_get_benchmark_pack_loader() -> None:
    """Register a benchmark pack loader stub and get it."""
    from labtrust_gym.benchmarks.official_pack import (
        get_benchmark_pack_loader,
        register_benchmark_pack_loader,
    )

    def _stub_loader(repo_root: Path, prefer_v02: bool, partner_id: str | None) -> tuple[dict[str, Any], str, str]:
        return ({"version": "0.1", "tasks": {"core": []}}, "0.1", "stub")

    lid = _stub_pack_loader_id()
    register_benchmark_pack_loader(lid, _stub_loader)
    try:
        got = get_benchmark_pack_loader(lid)
        assert got is _stub_loader
    finally:
        from labtrust_gym.benchmarks.official_pack import _BENCHMARK_PACK_LOADERS

        _BENCHMARK_PACK_LOADERS.pop(lid, None)


# ----- Profile integration: provider_id passed through -----


def test_profile_provider_id_passed_to_run_security_suite(tmp_path: Path) -> None:
    """When profile sets security_suite_provider_id, it is passed into run_security_suite."""
    from labtrust_gym.benchmarks.security_runner import (
        get_security_suite_provider,
        register_security_suite_provider,
        run_security_suite,
    )

    called: list[str] = []

    class StubProvider:
        def run_suite(
            self,
            policy_root: Path,
            repo_root: Path,
            smoke_only: bool = True,
            seed: int = 42,
            timeout_s: int = 120,
            llm_attacker: bool = False,
            allow_network: bool = False,
            llm_backend: str | None = None,
            llm_model: str | None = None,
        ) -> list[dict[str, Any]]:
            called.append("run_suite")
            return [{"attack_id": "stub", "passed": True}]

    pid = _stub_security_provider_id()
    register_security_suite_provider(pid, StubProvider())
    try:
        run_security_suite(
            policy_root=tmp_path,
            repo_root=tmp_path,
            smoke_only=True,
            provider_id=pid,
        )
        assert called == ["run_suite"]
        assert get_security_suite_provider(pid) is not None
    finally:
        from labtrust_gym.benchmarks.security_runner import _SECURITY_SUITE_PROVIDERS

        _SECURITY_SUITE_PROVIDERS.pop(pid, None)


# ----- Config: path overrides centralized -----


def test_get_effective_path_uses_profile_when_set(tmp_path: Path) -> None:
    """get_effective_path returns profile path when set, else default under policy."""
    from labtrust_gym.config import get_effective_path

    policy_root = tmp_path
    default_rel = "golden/security_attack_suite.v0.1.yaml"
    # No profile / null field -> default under policy
    assert get_effective_path(policy_root, None, "security_suite_path", default_rel) == (
        policy_root / "policy" / default_rel
    )
    assert (
        get_effective_path(policy_root, {"other": "x"}, "security_suite_path", default_rel)
        == policy_root / "policy" / default_rel
    )
    # Profile has field -> resolved relative to policy_root
    profile_custom = {"security_suite_path": "policy/golden/custom_suite.v0.1.yaml"}
    got = get_effective_path(policy_root, profile_custom, "security_suite_path", default_rel)
    assert got == (policy_root / "policy" / "golden" / "custom_suite.v0.1.yaml").resolve()


def test_safety_case_provider_id_passed_through(tmp_path: Path) -> None:
    """When provider_id is set, build_safety_case uses the registered provider."""
    from labtrust_gym.security.safety_case import (
        build_safety_case,
        get_safety_case_provider,
        register_safety_case_provider,
    )

    called: list[str] = []

    class StubSafetyProvider:
        def build_safety_case(self, policy_root: Path) -> dict[str, Any]:
            called.append("build_safety_case")
            return {"version": "0.1", "claims": [], "source": "stub"}

    pid = _stub_safety_provider_id()
    register_safety_case_provider(pid, StubSafetyProvider())
    try:
        result = build_safety_case(tmp_path, provider_id=pid)
        assert called == ["build_safety_case"]
        assert result.get("source") == "stub"
        assert get_safety_case_provider(pid) is not None
    finally:
        from labtrust_gym.security.safety_case import _SAFETY_CASE_PROVIDERS

        _SAFETY_CASE_PROVIDERS.pop(pid, None)


def test_metrics_aggregator_resolution() -> None:
    """Registered metrics aggregator is resolved by get_metrics_aggregator."""
    from labtrust_gym.benchmarks.metrics import (
        get_metrics_aggregator,
        list_metrics_aggregators,
        register_metrics_aggregator,
    )

    def stub_aggregator(
        step_results_per_step: list,
        t_s_per_step: list | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {"throughput": 0, "stub": True}

    pid = _stub_metrics_aggregator_id()
    register_metrics_aggregator(pid, stub_aggregator)
    try:
        agg = get_metrics_aggregator(pid)
        assert agg is stub_aggregator
        assert pid in list_metrics_aggregators()
    finally:
        from labtrust_gym.benchmarks.metrics import _METRICS_AGGREGATORS

        _METRICS_AGGREGATORS.pop(pid, None)


# ----- Domain: resolution and validation -----


def _stub_domain_id() -> str:
    return f"{_MOD_PREFIX}domain"


def test_domain_adapter_factory_resolution() -> None:
    """Registered domain is resolved by get_domain_adapter_factory; list_domains includes it."""
    from labtrust_gym.domain import (
        get_domain_adapter_factory,
        list_domains,
        register_domain,
    )
    from labtrust_gym.runner.adapter import LabTrustEnvAdapter

    class StubAdapter(LabTrustEnvAdapter):
        def reset(self, initial_state: dict, *, deterministic: bool, rng_seed: int) -> None:
            pass

        def step(self, event: dict) -> dict:
            return {"status": "ACCEPTED", "emits": [], "hashchain": {}}

        def query(self, expr: str) -> Any:
            return None

    def stub_factory(workflow_spec: dict, config: dict | None = None) -> LabTrustEnvAdapter:
        return StubAdapter()

    did = _stub_domain_id()
    register_domain(did, stub_factory)
    try:
        factory = get_domain_adapter_factory(did)
        assert factory is stub_factory
        assert did in list_domains()
    finally:
        from labtrust_gym.domain.registry import _DOMAIN_REGISTRY

        _DOMAIN_REGISTRY.pop(did, None)


def test_unknown_domain_id_returns_none() -> None:
    """Unknown domain_id yields None; profile validation fails fast with list_domains()."""
    from labtrust_gym.domain import get_domain_adapter_factory, list_domains

    unknown = "_modularity_nonexistent_domain_"
    assert get_domain_adapter_factory(unknown) is None
    assert unknown not in list_domains()
    assert "hospital_lab" in list_domains()
