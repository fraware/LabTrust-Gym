"""
LTG-PR7: external agents and adapters against a pinned public release.

Exercises six offline integrations bound to ``benchmarks/external_integrations/pinned_release.v1.json``:

1. native scripted agent
2. Gymnasium wrapper
3. PettingZoo wrapper
4. external Python agent (``eval-agent`` / ``examples.external_agent_demo``)
5. one MARL baseline (``train-ppo`` / ``eval-ppo`` smoke; skip if ``[marl]`` missing)
6. one verifier-optimization workflow (VA-13 offline PPO vs ``V_public``; CI-safe numpy path)

No live proprietary LLM in the default path. ``[env]`` extras required for Gymnasium /
PettingZoo / eval-agent; missing extras skip cleanly.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from labtrust_gym.benchmarks.external_integrations import (
    PIN_REL_PATH,
    assert_pin_artifacts_present,
    load_baselines_metadata,
    load_pinned_baseline_results,
    load_pinned_release,
    pin_policy_digest,
    write_integration_evidence,
)
from labtrust_gym.config import get_repo_root
from labtrust_gym.export.reconstruction import compute_environment_digest

pytestmark = pytest.mark.timeout(180)

_MARL_SKIP_MSG = (
    "stable_baselines3/torch failed to load (DLL/runtime). "
    "Install CPU-only torch or matching CUDA wheels, or skip MARL integration."
)


def _repo() -> Path:
    return get_repo_root()


@pytest.fixture(scope="module")
def pin() -> dict:
    p = load_pinned_release(_repo())
    assert_pin_artifacts_present(p, _repo())
    return p


def test_pin_manifest_and_frozen_packs(pin: dict) -> None:
    """Pin file exists, digests match frozen baselines metadata, VA pack present."""
    root = _repo()
    assert (root / PIN_REL_PATH).is_file()
    assert pin["no_live_llm"] is True
    meta = load_baselines_metadata(pin, root)
    assert meta["baseline_version"] == pin["baselines_pack"]["baseline_version"]
    results = load_pinned_baseline_results(pin, root)
    assert results["schema_version"] == "0.2"
    assert results["pipeline_mode"] == "deterministic"
    assert results.get("allow_network") is False
    env_digest = compute_environment_digest(policy_digest=pin_policy_digest(pin))
    assert len(env_digest) == 64


def test_01_native_scripted_agent_against_pin(pin: dict, tmp_path: Path) -> None:
    """Scripted ops baseline runs against pin task/seed and writes reconstructable evidence."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.benchmarks.runner import run_benchmark

    pack = pin["baselines_pack"]
    smoke = pin["smoke"]
    out = tmp_path / "scripted_results.json"
    results = run_benchmark(
        task_name=str(pack["task"]),
        num_episodes=int(smoke["episodes"]),
        base_seed=int(pack["seed"]),
        out_path=out,
        repo_root=_repo(),
        timing_mode=str(pack["timing"]),
        pipeline_mode="deterministic",
        allow_network=False,
    )
    assert out.is_file()
    assert results["task"] == pack["task"]
    assert results["agent_baseline_id"] == pack["agent_baseline_id"]
    assert results["base_seed"] == pack["seed"]
    assert results.get("pipeline_mode") == "deterministic"
    assert results.get("allow_network") is False
    assert len(results.get("episodes") or []) == int(smoke["episodes"])

    frozen = load_pinned_baseline_results(pin, _repo())
    assert frozen["agent_baseline_id"] == results["agent_baseline_id"]
    assert frozen["base_seed"] == results["base_seed"]

    bundle = write_integration_evidence(
        tmp_path / "scripted_evidence",
        pin=pin,
        agent_identity=str(results["agent_baseline_id"]),
        seed=int(pack["seed"]),
        scenario_ids=[str(pack["task"])],
        integration_id="native_scripted",
    )
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["reconstruction"]["policy_digest"] == pin_policy_digest(pin)
    assert manifest["reconstruction"]["agent_identity"] == pack["agent_baseline_id"]
    assert manifest["reconstruction"]["seed"] == pack["seed"]


def test_02_gymnasium_wrapper_against_pin(pin: dict, tmp_path: Path) -> None:
    """Gymnasium wrapper resets with pin seed and steps offline."""
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    from labtrust_gym.baselines.marl.sb3_wrapper import LabTrustGymnasiumWrapper
    from labtrust_gym.envs.pz_parallel import LabTrustParallelEnv

    if LabTrustGymnasiumWrapper is None:
        pytest.skip("LabTrustGymnasiumWrapper requires gymnasium")

    pack = pin["baselines_pack"]
    smoke = pin["smoke"]
    raw = LabTrustParallelEnv(num_runners=1)
    env = LabTrustGymnasiumWrapper(raw, max_steps=int(smoke["env_max_steps"]), num_action_types=6)
    try:
        obs, info = env.reset(seed=int(pack["seed"]))
        assert obs is not None
        for _ in range(int(smoke["env_max_steps"])):
            action = env.action_space.sample()
            obs, reward, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                break
    finally:
        env.close()
        raw.close()

    bundle = write_integration_evidence(
        tmp_path / "gym_evidence",
        pin=pin,
        agent_identity="labtrust_gymnasium_wrapper",
        seed=int(pack["seed"]),
        scenario_ids=[str(pack["task"])],
        integration_id="gymnasium_wrapper",
    )
    recon = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["reconstruction"]
    assert recon["policy_digest"] == pin_policy_digest(pin)
    assert recon["seed"] == pack["seed"]


def test_03_pettingzoo_wrapper_against_pin(pin: dict, tmp_path: Path) -> None:
    """PettingZoo parallel env resets with pin seed and steps offline."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.envs.pz_parallel import ACTION_TICK, LabTrustParallelEnv

    pack = pin["baselines_pack"]
    smoke = pin["smoke"]
    env = LabTrustParallelEnv(num_runners=1)
    try:
        observations, infos = env.reset(seed=int(pack["seed"]))
        assert observations
        for _ in range(int(smoke["env_max_steps"])):
            if not env.agents:
                break
            actions = {a: ACTION_TICK for a in env.agents}
            observations, rewards, terminations, truncations, infos = env.step(actions)
            if all(terminations.get(a) or truncations.get(a) for a in list(terminations)):
                break
    finally:
        env.close()

    bundle = write_integration_evidence(
        tmp_path / "pz_evidence",
        pin=pin,
        agent_identity="labtrust_parallel_env",
        seed=int(pack["seed"]),
        scenario_ids=[str(pack["task"])],
        integration_id="pettingzoo_wrapper",
    )
    recon = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["reconstruction"]
    assert recon["policy_digest"] == pin_policy_digest(pin)


def test_04_external_python_agent_against_pin(pin: dict, tmp_path: Path) -> None:
    """External SafeNoOpAgent via eval-agent against pin task/seed; reconstructable evidence."""
    pytest.importorskip("pettingzoo")
    pytest.importorskip("gymnasium")
    from labtrust_gym.cli.eval_agent import run_eval_agent

    pack = pin["baselines_pack"]
    smoke = pin["smoke"]
    out = tmp_path / "external_results.json"
    results = run_eval_agent(
        task=str(pack["task"]),
        episodes=int(smoke["episodes"]),
        agent_spec="examples.external_agent_demo:SafeNoOpAgent",
        out_path=out,
        seed=int(pack["seed"]),
        timing=str(pack["timing"]),
        repo_root=_repo(),
        pipeline_mode="deterministic",
        allow_network=False,
    )
    assert out.is_file()
    assert results["task"] == pack["task"]
    assert results["base_seed"] == pack["seed"]
    assert "external_agent_demo" in str(results.get("agent_baseline_id") or "")
    assert results.get("pipeline_mode") == "deterministic"
    assert results.get("allow_network") is False

    bundle = write_integration_evidence(
        tmp_path / "external_evidence",
        pin=pin,
        agent_identity=str(results["agent_baseline_id"]),
        seed=int(pack["seed"]),
        scenario_ids=[str(pack["task"])],
        integration_id="external_python_agent",
    )
    recon = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["reconstruction"]
    assert recon["policy_digest"] == pin_policy_digest(pin)
    assert recon["agent_identity"] == results["agent_baseline_id"]


def _require_sb3_or_skip() -> None:
    try:
        result = subprocess.run(
            [sys.executable, "-c", "import stable_baselines3"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        pytest.skip("stable_baselines3 import timed out")
    except Exception as e:
        pytest.skip(f"Could not probe stable_baselines3: {e}")
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[:400]
        if "1114" in err or "DLL" in err or "c10" in err.lower() or "access violation" in err.lower():
            pytest.skip(_MARL_SKIP_MSG + (f" Raw: {err[:200]}" if err else ""))
        pytest.skip(f"stable_baselines3 not available ([marl] extra): {err or result.returncode}")


def test_05_marl_ppo_smoke_against_pin(pin: dict, tmp_path: Path) -> None:
    """train-ppo / eval-ppo smoke against pin task/seed; skip if [marl] missing."""
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    _require_sb3_or_skip()

    # On Windows, avoid importing torch in the main pytest process (DLL crash risk).
    if sys.platform == "win32" and os.environ.get("LTG_PR7_MARL_INLINE") != "1":
        env = {**os.environ, "LTG_PR7_MARL_INLINE": "1"}
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(Path(__file__).resolve()),
                "-v",
                "--tb=short",
                "-k",
                "test_05_marl_ppo_smoke_against_pin",
            ],
            env=env,
            timeout=300,
            cwd=str(_repo()),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            out = (result.stdout or "") + (result.stderr or "")
            if "1114" in out or "c10.dll" in out.lower() or "DLL" in out or "access violation" in out.lower():
                pytest.skip(_MARL_SKIP_MSG)
            if "SKIPPED" in out and "stable_baselines3" in out:
                pytest.skip("stable_baselines3 unavailable in subprocess")
            pytest.fail(f"MARL pin smoke failed in subprocess (exit {result.returncode})\n{out[-2000:]}")
        return

    from labtrust_gym.baselines.marl.ppo_eval import eval_ppo
    from labtrust_gym.baselines.marl.ppo_train import train_ppo

    pack = pin["baselines_pack"]
    smoke = pin["smoke"]
    out_dir = tmp_path / "ppo"
    train_result = train_ppo(
        task_name=str(pack["task"]),
        timesteps=int(smoke["marl_timesteps"]),
        seed=int(pack["seed"]),
        out_dir=out_dir,
        log_interval=max(1, int(smoke["marl_timesteps"])),
        verbose=0,
    )
    model_path = Path(train_result["model_path"])
    assert model_path.is_file()
    metrics = eval_ppo(
        model_path=str(model_path),
        task_name=str(pack["task"]),
        episodes=int(smoke["marl_eval_episodes"]),
        seed=int(pack["seed"]),
        out_path=tmp_path / "ppo_eval.json",
    )
    assert "mean_reward" in metrics
    assert (tmp_path / "ppo_eval.json").is_file()

    bundle = write_integration_evidence(
        tmp_path / "marl_evidence",
        pin=pin,
        agent_identity="marl_ppo_smoke",
        seed=int(pack["seed"]),
        scenario_ids=[str(pack["task"])],
        integration_id="marl_ppo",
    )
    recon = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["reconstruction"]
    assert recon["policy_digest"] == pin_policy_digest(pin)


def test_06_va13_offline_ppo_against_pin(pin: dict, tmp_path: Path) -> None:
    """VA-13 offline numpy PPO vs V_public; reconstruct VA pack (fresh build + pin identity)."""
    from labtrust_gym.verifier_assurance.calibration.aggregate import build_va_release_pack
    from labtrust_gym.verifier_assurance.campaign.export import reconstruct_campaign
    from labtrust_gym.verifier_assurance.oracle.dual_oracle import PublicVerifier, default_public_profile
    from labtrust_gym.verifier_assurance.training.offline_ppo import (
        OfflinePPOConfig,
        train_policy_against_public,
    )

    pack = pin["baselines_pack"]
    smoke = pin["smoke"]
    va = pin["va_release_pack"]
    pub = PublicVerifier(default_public_profile())
    cfg = OfflinePPOConfig(
        seed=int(smoke["va13_seed"]),
        episodes=int(smoke["va13_episodes"]),
        horizon=int(smoke["va13_horizon"]),
        checkpoint_dir=tmp_path / "va13_ckpts",
        backend="numpy_ppo",
    )
    trained = train_policy_against_public(pub, policy_id="ltg-pr7-va13", config=cfg)
    assert trained.checkpoint.backend == "numpy_ppo"
    assert trained.checkpoint.trained_against.startswith("V_public")
    assert trained.checkpoint.logits_digest
    assert "simulation_research_only" in (trained.checkpoint.claim_boundary or "")

    # Bind reconstruction evidence to the same official baselines pin identity.
    bundle = write_integration_evidence(
        tmp_path / "va13_evidence",
        pin=pin,
        agent_identity="va13_offline_ppo",
        seed=int(pack["seed"]),
        scenario_ids=[str(pack["task"]), "VA-13"],
        integration_id="va13_offline_ppo",
    )
    recon = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))["reconstruction"]
    assert recon["policy_digest"] == pin_policy_digest(pin)
    assert "VA-13" in recon["scenario_ids"]

    # Pin identity: committed path must declare the expected campaign_id.
    va_dir = _repo() / str(va["path"])
    release = json.loads((va_dir / "release_manifest.json").read_text(encoding="utf-8"))
    assert release.get("campaign_id") == va["campaign_id"]

    # Reconstruct a freshly built pack (CI-safe; avoids relying on dirty working-tree checksums).
    fresh = tmp_path / "va_release_fresh"
    built = build_va_release_pack(fresh)
    assert built["campaign_id"] == va["campaign_id"]
    reconstructed = reconstruct_campaign(fresh)
    assert reconstructed["valid"] is True, f"VA pack reconstruct failed: {reconstructed}"
    assert reconstructed.get("campaign_id") == va["campaign_id"]
