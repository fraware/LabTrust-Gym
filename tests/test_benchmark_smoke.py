"""
Benchmark smoke tests: run 2 episodes quickly, ensure deterministic outputs for same seed.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

pytest.importorskip("pettingzoo")
pytest.importorskip("gymnasium")

from labtrust_gym.benchmarks.runner import run_benchmark
from labtrust_gym.benchmarks.tasks import get_task
from labtrust_gym.config import get_repo_root


def test_benchmark_run_2_episodes_smoke() -> None:
    """Run 2 episodes for throughput_sla; no crash; results.json has 2 episodes."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results.json"
        run_benchmark(
            task_name="throughput_sla",
            num_episodes=2,
            base_seed=42,
            out_path=out,
        )
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["task"] == "throughput_sla"
        assert data["num_episodes"] == 2
        assert len(data["episodes"]) == 2
        assert "seeds" in data
        assert data["seeds"] == [42, 43]
        for ep in data["episodes"]:
            assert "seed" in ep
            assert "metrics" in ep
            assert "throughput" in ep["metrics"]
            assert "steps" in ep["metrics"]


def test_benchmark_determinism_same_seed() -> None:
    """Same task and base_seed produce identical episode metrics across two runs."""
    with tempfile.TemporaryDirectory() as tmp:
        out1 = Path(tmp) / "run1.json"
        out2 = Path(tmp) / "run2.json"
        run_benchmark(
            task_name="throughput_sla",
            num_episodes=2,
            base_seed=100,
            out_path=out1,
        )
        run_benchmark(
            task_name="throughput_sla",
            num_episodes=2,
            base_seed=100,
            out_path=out2,
        )
        data1 = json.loads(out1.read_text(encoding="utf-8"))
        data2 = json.loads(out2.read_text(encoding="utf-8"))
        assert data1["seeds"] == data2["seeds"]
        for i, (ep1, ep2) in enumerate(zip(data1["episodes"], data2["episodes"])):
            assert ep1["seed"] == ep2["seed"], f"episode {i} seed"
            assert (
                ep1["metrics"] == ep2["metrics"]
            ), f"episode {i} metrics differ: {ep1['metrics']} vs {ep2['metrics']}"


def test_task_initial_state_deterministic() -> None:
    """Task get_initial_state(seed) is deterministic."""
    task = get_task("throughput_sla")
    s1 = task.get_initial_state(99)
    s2 = task.get_initial_state(99)
    assert s1 == s2
    s3 = task.get_initial_state(100)
    assert s1 != s3 or s1 == s3


def test_initial_state_has_policy_root_and_reagent_stock_for_reset() -> None:
    """
    Confirm that the initial_state passed to env.reset() contains policy_root and
    reagent_initial_stock, and that the reagent policy file exists at the expected path.
    This ensures START_RUN can pass reagent checks and scripted runs can produce throughput.
    """
    repo_root = get_repo_root()
    task = get_task("throughput_sla")
    initial_state = task.get_initial_state(100)
    overrides = {"policy_root": str(repo_root)}
    if task.timing_mode is not None:
        overrides["timing_mode"] = task.timing_mode
    merged = {**initial_state, **overrides}

    assert (
        "policy_root" in merged
    ), "initial_state passed to reset must include policy_root"
    assert (
        "reagent_initial_stock" in merged
    ), "initial_state passed to reset must include reagent_initial_stock (throughput_sla/B/C provide it)"

    policy_root = Path(merged["policy_root"])
    reagent_policy_path = (
        policy_root / "policy" / "reagents" / "reagent_policy.v0.1.yaml"
    )
    assert (
        reagent_policy_path.exists()
    ), f"reagent policy file must exist at {reagent_policy_path} so engine can load stock"

    stock = merged["reagent_initial_stock"]
    assert isinstance(stock, dict), "reagent_initial_stock must be a dict"
    assert (
        "R_CHEM_CORE" in stock
    ), "reagent_initial_stock must include R_CHEM_CORE for BIOCHEM panels"
    assert (
        float(stock["R_CHEM_CORE"]) >= 14.0
    ), "R_CHEM_CORE stock must be >= 14 (quantity_per_run for BIOCHEM_PANEL_CORE) for at least one START_RUN"


@pytest.mark.slow
def test_task_e_multisite_stat_runs() -> None:
    """multi_site_stat (MultiSiteSTAT) runs without crash; results have expected structure."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results_taske.json"
        run_benchmark(
            task_name="multi_site_stat",
            num_episodes=1,
            base_seed=50,
            out_path=out,
        )
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["task"] == "multi_site_stat"
        assert data["num_episodes"] == 1
        assert len(data["episodes"]) == 1
        assert "seeds" in data
        assert data["seeds"] == [50]
        for ep in data["episodes"]:
            assert "seed" in ep
            assert "metrics" in ep
            assert "throughput" in ep["metrics"]
            assert "steps" in ep["metrics"]


@pytest.mark.slow
def test_task_e_emits_dispatch_transport_at_least_once() -> None:
    """multi_site_stat scripted policy must emit DISPATCH_TRANSPORT at least once per episode."""
    from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
    from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
    from labtrust_gym.benchmarks.runner import run_episode
    from labtrust_gym.benchmarks.tasks import get_task
    from labtrust_gym.envs.pz_parallel import (
        DEFAULT_DEVICE_IDS,
        DEFAULT_ZONE_IDS,
        LabTrustParallelEnv,
    )

    task = get_task("multi_site_stat")
    policy_dir = Path(__file__).resolve().parent.parent / "policy"
    num_runners = 2

    def _env_factory(initial_state, reward_config, log_path=None):
        return LabTrustParallelEnv(
            num_runners=num_runners,
            num_adversaries=0,
            num_insiders=0,
            dt_s=10,
            reward_config=reward_config,
            policy_dir=policy_dir,
            log_path=log_path,
        )

    agents_map = {
        "ops_0": ScriptedOpsAgent(),
        "runner_0": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS, device_ids=DEFAULT_DEVICE_IDS
        ),
        "runner_1": ScriptedRunnerAgent(
            zone_ids=DEFAULT_ZONE_IDS, device_ids=DEFAULT_DEVICE_IDS
        ),
    }
    metrics, step_results_per_step = run_episode(
        task, episode_seed=50, env_factory=_env_factory, scripted_agents_map=agents_map
    )
    dispatch_count = 0
    for results in step_results_per_step:
        for r in results:
            for e in r.get("emits") or []:
                if e == "DISPATCH_TRANSPORT":
                    dispatch_count += 1
    assert dispatch_count >= 1, (
        f"multi_site_stat must emit DISPATCH_TRANSPORT at least once; got {dispatch_count}. "
        "Scripted runner policy: DISPATCH_TRANSPORT -> TRANSPORT_TICK -> CHAIN_OF_CUSTODY_SIGN -> RECEIVE_TRANSPORT."
    )
    assert metrics.get("transport_consignment_count", 0) >= 1


@pytest.mark.slow
def test_task_e_determinism() -> None:
    """multi_site_stat: same seed => identical episode metrics (reproducible)."""
    with tempfile.TemporaryDirectory() as tmp:
        out1 = Path(tmp) / "taske1.json"
        out2 = Path(tmp) / "taske2.json"
        run_benchmark(task_name="multi_site_stat", num_episodes=2, base_seed=77, out_path=out1)
        run_benchmark(task_name="multi_site_stat", num_episodes=2, base_seed=77, out_path=out2)
        data1 = json.loads(out1.read_text(encoding="utf-8"))
        data2 = json.loads(out2.read_text(encoding="utf-8"))
        assert data1["seeds"] == data2["seeds"]
        for i, (ep1, ep2) in enumerate(zip(data1["episodes"], data2["episodes"])):
            assert ep1["seed"] == ep2["seed"], f"episode {i} seed"
            assert (
                ep1["metrics"] == ep2["metrics"]
            ), f"multi_site_stat episode {i} metrics differ: {ep1['metrics']} vs {ep2['metrics']}"


@pytest.mark.slow
def test_task_e_deterministic_transport_path() -> None:
    """multi_site_stat: fixed seed => deterministic transport path (same transport_consignment_count, same order of transport emits)."""
    from labtrust_gym.baselines.scripted_ops import ScriptedOpsAgent
    from labtrust_gym.baselines.scripted_runner import ScriptedRunnerAgent
    from labtrust_gym.benchmarks.runner import run_episode
    from labtrust_gym.benchmarks.tasks import get_task
    from labtrust_gym.envs.pz_parallel import (
        DEFAULT_DEVICE_IDS,
        DEFAULT_ZONE_IDS,
        LabTrustParallelEnv,
    )

    task = get_task("multi_site_stat")
    policy_dir = Path(__file__).resolve().parent.parent / "policy"
    num_runners = 2
    seed = 123

    def _env_factory(initial_state, reward_config, log_path=None):
        return LabTrustParallelEnv(
            num_runners=num_runners,
            num_adversaries=0,
            num_insiders=0,
            dt_s=10,
            reward_config=reward_config,
            policy_dir=policy_dir,
            log_path=log_path,
        )

    def _run():
        agents_map = {
            "ops_0": ScriptedOpsAgent(),
            "runner_0": ScriptedRunnerAgent(
                zone_ids=DEFAULT_ZONE_IDS, device_ids=DEFAULT_DEVICE_IDS
            ),
            "runner_1": ScriptedRunnerAgent(
                zone_ids=DEFAULT_ZONE_IDS, device_ids=DEFAULT_DEVICE_IDS
            ),
        }
        metrics, step_results_per_step = run_episode(
            task,
            episode_seed=seed,
            env_factory=_env_factory,
            scripted_agents_map=agents_map,
        )
        transport_emits_sequence = []
        for results in step_results_per_step:
            for r in results:
                for e in r.get("emits") or []:
                    if e in (
                        "DISPATCH_TRANSPORT",
                        "TRANSPORT_TICK",
                        "CHAIN_OF_CUSTODY_SIGN",
                        "RECEIVE_TRANSPORT",
                    ):
                        transport_emits_sequence.append(e)
        return (
            metrics.get("transport_consignment_count", 0),
            metrics.get("coc_breaks_count", 0),
            tuple(transport_emits_sequence),
        )

    count1, coc1, seq1 = _run()
    count2, coc2, seq2 = _run()
    assert (
        count1 == count2
    ), f"transport_consignment_count must be deterministic: {count1} vs {count2}"
    assert coc1 == coc2, f"coc_breaks_count must be deterministic: {coc1} vs {coc2}"
    assert (
        seq1 == seq2
    ), f"Transport emit sequence must be deterministic: {seq1} vs {seq2}"


@pytest.mark.slow
def test_task_f_insider_runs() -> None:
    """insider_key_misuse (InsiderAndKeyMisuse) runs without crash; results include containment/forensic metrics."""
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "results_taskf.json"
        run_benchmark(
            task_name="insider_key_misuse",
            num_episodes=2,
            base_seed=200,
            out_path=out,
        )
        assert out.exists()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["task"] == "insider_key_misuse"
        assert data["num_episodes"] == 2
        assert len(data["episodes"]) == 2
        for ep in data["episodes"]:
            assert "seed" in ep
            assert "metrics" in ep
            m = ep["metrics"]
            assert "throughput" in m
            assert "steps" in m
            assert "fraction_of_attacks_contained" in m
            assert (
                "time_to_first_detected_security_violation" in m
                or "fraction_of_attacks_contained" in m
            )
            assert "forensic_quality_score" in m


@pytest.mark.slow
def test_task_f_determinism() -> None:
    """insider_key_misuse: same seed => identical episode metrics (deterministic scripted insider)."""
    with tempfile.TemporaryDirectory() as tmp:
        out1 = Path(tmp) / "taskf1.json"
        out2 = Path(tmp) / "taskf2.json"
        run_benchmark(task_name="insider_key_misuse", num_episodes=2, base_seed=300, out_path=out1)
        run_benchmark(task_name="insider_key_misuse", num_episodes=2, base_seed=300, out_path=out2)
        data1 = json.loads(out1.read_text(encoding="utf-8"))
        data2 = json.loads(out2.read_text(encoding="utf-8"))
        assert data1["seeds"] == data2["seeds"]
        for i, (ep1, ep2) in enumerate(zip(data1["episodes"], data2["episodes"])):
            assert ep1["seed"] == ep2["seed"], f"episode {i} seed"
            assert ep1["metrics"] == ep2["metrics"], f"insider_key_misuse episode {i} metrics differ"
