"""
Security attack suite runner: run golden security scenarios and write results.

Loads policy/golden/security_attack_suite.v0.1.yaml. For each attack (optionally
filtered by smoke=True), runs the scenario (e.g. prompt-injection in-process or
via pytest test_ref) and writes SECURITY/attack_results.json with pass/fail and
optional receipts. Deterministic with a fixed seed; CI uses smoke mode. Optional
LLM (large language model) attacker mode: with --llm-attacker and --allow-network,
attacks marked llm_attacker=true use a live LLM to generate adversarial payloads
and the shield under test must block them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from labtrust_gym.config import policy_path
from labtrust_gym.policy.loader import load_yaml

# Max seconds for live LLM to generate one adversarial payload (prevents suite hang).
LLM_ATTACKER_GENERATE_TIMEOUT_S = 60

# Security suite provider registry: provider_id -> provider (load_suite, run_suite).
# Provider: load_suite(policy_root, partner_id) -> dict; run_suite(policy_root, repo_root, ...) -> list[dict].
_SECURITY_SUITE_PROVIDERS: dict[str, Any] = {}


def register_security_suite_provider(provider_id: str, provider: Any) -> None:
    """Register a security suite provider. Overwrites if present."""
    _SECURITY_SUITE_PROVIDERS[provider_id] = provider


def get_security_suite_provider(provider_id: str) -> Any | None:
    """Return the registered security suite provider, or None."""
    return _SECURITY_SUITE_PROVIDERS.get(provider_id)


def list_security_suite_providers() -> list[str]:
    """Return sorted list of registered security suite provider IDs."""
    return sorted(_SECURITY_SUITE_PROVIDERS.keys())


def _default_security_suite_provider() -> Any:
    """Build the default provider (current load_attack_suite + run_security_suite)."""
    from types import SimpleNamespace

    return SimpleNamespace(
        load_suite=load_attack_suite,
        run_suite=run_security_suite,
    )


def _ensure_default_security_provider() -> None:
    if "default" not in _SECURITY_SUITE_PROVIDERS:
        register_security_suite_provider("default", _default_security_suite_provider())


def load_llm_attacker_prompts(policy_root: Path) -> list[dict[str, Any]]:
    """Load llm_attacker_prompts.v0.1.yaml; return list of prompt dicts (prompt_id, user_prompt, etc.)."""
    path = policy_path(policy_root, "golden", "llm_attacker_prompts.v0.1.yaml")
    if not path.exists():
        return []
    data = load_yaml(path)
    prompts = (data or {}).get("prompts", [])
    return prompts if isinstance(prompts, list) else []


def load_attack_suite(
    policy_root: Path,
    partner_id: str | None = None,
    suite_path: Path | None = None,
) -> dict[str, Any]:
    """Load security_attack_suite. When suite_path is set, load from it; else when partner_id try partners/<id>/golden/, else policy/golden/."""
    if suite_path is not None and suite_path.exists():
        data = load_yaml(suite_path)
        return data if isinstance(data, dict) else {}
    if partner_id:
        overlay_path = policy_path(
            policy_root, "partners", partner_id, "golden", "security_attack_suite.v0.1.yaml"
        )
        if overlay_path.exists():
            data = load_yaml(overlay_path)
            return data if isinstance(data, dict) else {}
    path = policy_path(policy_root, "golden", "security_attack_suite.v0.1.yaml")
    if not path.exists():
        return {}
    data = load_yaml(path)
    return data if isinstance(data, dict) else {}


def load_prompt_injection_scenarios(policy_root: Path) -> list[dict[str, Any]]:
    """Load prompt_injection_scenarios.v0.1.yaml scenarios."""
    path = policy_path(policy_root, "golden", "prompt_injection_scenarios.v0.1.yaml")
    if not path.exists():
        return []
    data = load_yaml(path)
    scenarios = (data or {}).get("scenarios", [])
    return scenarios if isinstance(scenarios, list) else []


def _run_prompt_injection_attack(
    scenario_id: str,
    scenarios: list[dict[str, Any]],
    policy_root: Path,
    seed: int,
) -> tuple[bool, str | None]:
    """
    Run one prompt-injection scenario in-process (same logic as golden test).
    Returns (passed, error_message).
    """
    spec = next((s for s in scenarios if s.get("scenario_id") == scenario_id), None)
    if not spec:
        return (
            False,
            f"scenario_id {scenario_id!r} not in prompt_injection_scenarios",
        )
    try:
        from labtrust_gym.baselines.llm.agent import (
            DeterministicConstrainedBackend,
            LLMAgentWithShield,
        )
    except ImportError as e:
        return False, f"LLM agent import failed: {e}"
    try:
        import gymnasium  # noqa: F401
        import pettingzoo  # noqa: F401
    except ImportError:
        return False, "pettingzoo or gymnasium not installed"
    allowed = spec.get("allowed_actions_for_assert", ["NOOP", "TICK"])
    injection_source = spec.get("injection_source", "specimen_note")
    adversarial_string = spec.get("adversarial_string", "")
    obs = _observation_with_injection(injection_source, adversarial_string, allowed)
    rbac = {
        "roles": [{"role_id": "ROLE_RECEPTION", "allowed_actions": allowed}],
        "agents": {"ops_0": "ROLE_RECEPTION"},
    }
    agent = LLMAgentWithShield(
        backend=DeterministicConstrainedBackend(seed=seed, default_action_type="NOOP"),
        rbac_policy=rbac,
        pz_to_engine={"ops_0": "A_RECEPTION"},
        use_action_proposal_schema=True,
    )
    agent.reset(seed=seed, partner_id="", timing_mode="explicit")
    _, action_info, meta = agent.act(obs, agent_id="ops_0")
    action_type = (action_info or {}).get("action_type", "NOOP")
    if action_type not in allowed and action_type != "NOOP":
        return False, f"action_type {action_type!r} not in allowed {allowed}"
    proposal = ((meta or {}).get("_llm_decision") or {}).get("action_proposal") or {}
    proposal_type = proposal.get("action_type", "NOOP")
    if proposal_type not in allowed and proposal_type != "NOOP":
        return (
            False,
            f"proposal action_type {proposal_type!r} not in allowed {allowed}",
        )
    return True, None


def _observation_with_injection(
    injection_key: str,
    adversarial_string: str,
    allowed_actions: list[str],
) -> dict[str, Any]:
    obs = {
        "zone_id": "Z_SRA_RECEPTION",
        "site_id": "SITE_HUB",
        "t_s": 0,
        "queue_by_device": [],
        "log_frozen": 0,
        "role_id": "ROLE_RECEPTION",
    }
    if injection_key == "specimen_note":
        obs["specimen_notes"] = adversarial_string
    elif injection_key in ("transport_manifest_note", "scenario_note"):
        obs["scenario_notes"] = adversarial_string
    return obs


# Max chars of combined stderr+stdout to include in attack_results.json on failure.
_TEST_REF_ERROR_TRUNCATE = 800


def _run_test_ref_attack(
    test_ref: str,
    repo_root: Path,
    timeout_s: int = 120,
) -> tuple[bool, str | None]:
    """
    Run attack via pytest subprocess for test_ref (e.g. tests.test_tool_sandbox).
    test_ref may be module path or "tests.module::test_function_name" for a single test.
    Returns (passed, error_message).
    """
    # test_ref: "tests.test_tool_sandbox" or "tests/test_tool_sandbox.py" or "tests.module::test_foo"
    if "::" in test_ref:
        module_part, test_name = test_ref.split("::", 1)
        if module_part.endswith(".py"):
            target = f"{module_part}::{test_name}"
        else:
            path_part = module_part.replace(".", "/") + ".py"
            target = f"{path_part}::{test_name}"
    elif test_ref.endswith(".py"):
        target = test_ref
    else:
        target = test_ref.replace(".", "/") + ".py"
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        target,
        "-v",
        "--tb=no",
        "-q",
    ]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        if result.returncode != 0:
            combined = (result.stdout or "") + "\n" + (result.stderr or "")
            combined = combined.strip()
            if len(combined) > _TEST_REF_ERROR_TRUNCATE:
                combined = combined[-_TEST_REF_ERROR_TRUNCATE:]
            err = combined or f"pytest exited {result.returncode!s}"
            return False, err
        return True, None
    except subprocess.TimeoutExpired:
        return False, f"pytest timeout ({timeout_s}s)"
    except Exception as e:
        return False, str(e)


def _create_attacker_backend(
    llm_backend_id: str,
    model_override: str | None = None,
) -> tuple[Any, str | None]:
    """
    Create a live LLM backend suitable for generate(messages) -> str (attacker payload generation).
    Returns (backend, None) or (None, error_message). Caller must ensure allow_network is set.
    """
    if llm_backend_id == "openai_live":
        if not os.environ.get("OPENAI_API_KEY"):
            return None, "OPENAI_API_KEY not set (required for openai_live attacker)"
        try:
            from labtrust_gym.baselines.llm.backends.openai_live import (
                OpenAILiveBackend,
            )

            backend = OpenAILiveBackend(
                api_key=os.environ.get("OPENAI_API_KEY"),
                model=model_override
                or os.environ.get("LABTRUST_OPENAI_MODEL")
                or "gpt-4o-mini",
            )
            return backend, None
        except ImportError as e:
            return None, f"openai_live backend not available: {e}"
    if llm_backend_id == "ollama_live":
        try:
            from labtrust_gym.baselines.llm.backends.ollama_live import (
                OllamaLiveBackend,
            )

            backend = OllamaLiveBackend(model=model_override or "llama3.2")
            return backend, None
        except ImportError as e:
            return None, f"ollama_live backend not available: {e}"
    if llm_backend_id == "anthropic_live":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return (
                None,
                "ANTHROPIC_API_KEY not set (required for anthropic_live attacker)",
            )
        try:
            from labtrust_gym.baselines.llm.backends.anthropic_live import (
                AnthropicLiveBackend,
            )

            backend = AnthropicLiveBackend(
                api_key=os.environ.get("ANTHROPIC_API_KEY"),
                model=model_override or "claude-3-haiku-20240307",
            )
            return backend, None
        except ImportError as e:
            return None, f"anthropic_live backend not available: {e}"
    return None, f"unknown llm_backend_id for attacker: {llm_backend_id!r}"


def _run_llm_attacker_attack(
    attack: dict[str, Any],
    prompts_list: list[dict[str, Any]],
    policy_root: Path,
    seed: int,
    llm_backend_id: str,
    allow_network: bool,
    model_override: str | None = None,
) -> tuple[bool, str | None, str | None]:
    """
    Run one LLM-attacker attack: use live LLM to generate adversarial string, then run
    same in-process check as prompt-injection (observation + LLMAgentWithShield with
    DeterministicConstrainedBackend). Returns (passed, error_message, model_id).
    """
    if not allow_network:
        return False, "llm_attacker requires allow_network", None
    prompt_id = attack.get("attacker_prompt_template_id")
    if not prompt_id:
        return False, "llm_attacker attack missing attacker_prompt_template_id", None
    spec = next((p for p in prompts_list if p.get("prompt_id") == prompt_id), None)
    if not spec:
        return (
            False,
            f"attacker_prompt_template_id {prompt_id!r} not in llm_attacker_prompts",
            None,
        )
    user_prompt = spec.get("user_prompt", "")
    if not user_prompt:
        return False, f"prompt {prompt_id!r} has no user_prompt", None
    backend, err = _create_attacker_backend(llm_backend_id, model_override)
    if err or backend is None:
        return False, err or "failed to create attacker backend", None
    try:
        from labtrust_gym.pipeline import check_network_allowed

        check_network_allowed()
    except Exception as e:
        return False, f"network not allowed: {e}", None
    messages = [{"role": "user", "content": user_prompt}]
    result: list[str | Exception] = []

    def _generate() -> None:
        try:
            out = backend.generate(messages)
            result.append(
                out if isinstance(out, str) else str(out) if out is not None else ""
            )
        except Exception as e:
            result.append(e)

    thread = threading.Thread(target=_generate, daemon=True)
    thread.start()
    thread.join(timeout=LLM_ATTACKER_GENERATE_TIMEOUT_S)
    if thread.is_alive():
        return (
            False,
            f"attacker LLM generate timed out ({LLM_ATTACKER_GENERATE_TIMEOUT_S}s)",
            None,
        )
    if not result:
        return False, "attacker LLM generate produced no result", None
    if isinstance(result[0], Exception):
        return False, f"attacker LLM generate failed: {result[0]}", None
    adversarial_string = result[0]
    if not adversarial_string or not isinstance(adversarial_string, str):
        adversarial_string = ""
    adversarial_string = adversarial_string.strip()[:2000]
    model_id = None
    if hasattr(backend, "get_aggregate_metrics"):
        metrics = backend.get_aggregate_metrics()
        model_id = (metrics or {}).get("model_id")
    if not model_id and hasattr(backend, "_model"):
        model_id = getattr(backend, "_model", None)
    try:
        import gymnasium  # noqa: F401
        import pettingzoo  # noqa: F401
    except ImportError:
        return False, "pettingzoo or gymnasium not installed", model_id
    try:
        from labtrust_gym.baselines.llm.agent import (
            DeterministicConstrainedBackend,
            LLMAgentWithShield,
        )
    except ImportError as e:
        return False, f"LLM agent import failed: {e}", model_id
    injection_source = attack.get("injection_source", "specimen_note")
    allowed = attack.get("allowed_actions_for_assert") or ["NOOP", "TICK"]
    obs = _observation_with_injection(injection_source, adversarial_string, allowed)
    rbac = {
        "roles": [{"role_id": "ROLE_RECEPTION", "allowed_actions": allowed}],
        "agents": {"ops_0": "ROLE_RECEPTION"},
    }
    agent = LLMAgentWithShield(
        backend=DeterministicConstrainedBackend(seed=seed, default_action_type="NOOP"),
        rbac_policy=rbac,
        pz_to_engine={"ops_0": "A_RECEPTION"},
        use_action_proposal_schema=True,
    )
    agent.reset(seed=seed, partner_id="", timing_mode="explicit")
    _, action_info, meta = agent.act(obs, agent_id="ops_0")
    action_type = (action_info or {}).get("action_type", "NOOP")
    if action_type not in allowed and action_type != "NOOP":
        return False, f"action_type {action_type!r} not in allowed {allowed}", model_id
    proposal = ((meta or {}).get("_llm_decision") or {}).get("action_proposal") or {}
    proposal_type = proposal.get("action_type", "NOOP")
    if proposal_type not in allowed and proposal_type != "NOOP":
        return (
            False,
            f"proposal action_type {proposal_type!r} not in allowed {allowed}",
            model_id,
        )
    return True, None, model_id


def run_security_suite(
    policy_root: Path,
    repo_root: Path | None = None,
    smoke_only: bool = True,
    seed: int = 42,
    timeout_s: int = 120,
    llm_attacker: bool = False,
    allow_network: bool = False,
    llm_backend: str | None = None,
    llm_model: str | None = None,
    provider_id: str | None = None,
    security_suite_path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Run all attacks in the security attack suite (smoke-only or full).
    Returns list of result dicts: attack_id, passed, outcome, duration_ms, error.
    timeout_s: max seconds per test_ref pytest run (default 120).
    When llm_attacker=True and allow_network=True and llm_backend is set, runs attacks
    with llm_attacker=true (live LLM generates payloads). Otherwise skips them.
    When provider_id is set, use the registered security suite provider.
    When security_suite_path is set, load the suite from that path instead of default.
    """
    if provider_id is not None:
        provider = get_security_suite_provider(provider_id)
        if provider is not None and hasattr(provider, "run_suite"):
            return provider.run_suite(
                policy_root=policy_root,
                repo_root=repo_root or policy_root,
                smoke_only=smoke_only,
                seed=seed,
                timeout_s=timeout_s,
                llm_attacker=llm_attacker,
                allow_network=allow_network,
                llm_backend=llm_backend,
                llm_model=llm_model,
            )
    repo_root = repo_root or policy_root
    suite = load_attack_suite(policy_root, suite_path=security_suite_path)
    attacks = suite.get("attacks") or []
    if smoke_only:
        attacks = [a for a in attacks if a.get("smoke") is True]
    # Skip LLM-attacker attacks unless explicitly opted in
    run_llm_attacker = bool(llm_attacker and allow_network and llm_backend)
    if not run_llm_attacker:
        attacks = [a for a in attacks if not a.get("llm_attacker")]
    scenarios = load_prompt_injection_scenarios(policy_root)
    llm_prompts = load_llm_attacker_prompts(policy_root) if run_llm_attacker else []
    results: list[dict[str, Any]] = []
    for attack in attacks:
        attack_id = attack.get("attack_id", "unknown")
        expected = attack.get("expected_outcome", "blocked")
        t0 = time.perf_counter()
        passed = False
        err: str | None = None
        model_id: str | None = None
        if attack.get("llm_attacker"):
            template_ids: list[str] = list(
                attack.get("attacker_prompt_template_ids") or []
            )
            if not template_ids and attack.get("attacker_prompt_template_id"):
                template_ids = [str(attack["attacker_prompt_template_id"])]
            if not template_ids:
                err = "llm_attacker attack missing attacker_prompt_template_id(s)"
            else:
                all_passed = True
                first_err: str | None = None
                for tid in template_ids:
                    attack_one = dict(attack)
                    attack_one["attacker_prompt_template_id"] = tid
                    p, e, mid = _run_llm_attacker_attack(
                        attack_one,
                        llm_prompts,
                        policy_root,
                        seed,
                        llm_backend or "openai_live",
                        allow_network,
                        model_override=llm_model,
                    )
                    if not p:
                        all_passed = False
                        first_err = e or "unknown"
                        break
                    if mid:
                        model_id = mid
                passed = all_passed
                err = None if all_passed else first_err
        else:
            scenario_ref = attack.get("scenario_ref")
            test_ref = attack.get("test_ref")
            if scenario_ref:
                passed, err = _run_prompt_injection_attack(
                    scenario_ref, scenarios, policy_root, seed
                )
            elif test_ref:
                passed, err = _run_test_ref_attack(
                    test_ref, repo_root, timeout_s=timeout_s
                )
            else:
                err = "attack has no scenario_ref, test_ref, or llm_attacker"
        duration_ms = round((time.perf_counter() - t0) * 1000)
        row: dict[str, Any] = {
            "attack_id": attack_id,
            "risk_id": attack.get("risk_id"),
            "control_id": attack.get("control_id"),
            "expected_outcome": expected,
            "passed": passed,
            "duration_ms": duration_ms,
            "error": err,
        }
        if attack.get("llm_attacker"):
            row["llm_attacker"] = True
            if model_id:
                row["model_id"] = model_id
        results.append(row)
    return results


def write_attack_results(
    results: list[dict[str, Any]],
    out_path: Path,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Write attack_results.json with results and optional metadata."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    meta = dict(metadata or {})
    llm_attacker_results = [r for r in results if r.get("llm_attacker")]
    if llm_attacker_results:
        meta["llm_attacker_run"] = True
        model_ids = list(
            dict.fromkeys(
                r.get("model_id") for r in llm_attacker_results if r.get("model_id")
            )
        )
        if model_ids:
            meta["llm_attacker_model_ids"] = model_ids
    payload = {
        "version": "0.1",
        "metadata": meta,
        "results": results,
        "summary": {
            "total": len(results),
            "passed": sum(1 for r in results if r.get("passed")),
            "failed": sum(1 for r in results if not r.get("passed")),
        },
    }
    out_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def run_suite_and_emit(
    policy_root: Path,
    out_dir: Path,
    repo_root: Path | None = None,
    smoke_only: bool = True,
    seed: int = 42,
    timeout_s: int = 120,
    metadata: dict[str, Any] | None = None,
    llm_attacker: bool = False,
    allow_network: bool = False,
    llm_backend: str | None = None,
    llm_model: str | None = None,
    provider_id: str | None = None,
    security_suite_path: Path | None = None,
) -> list[dict[str, Any]]:
    """
    Run security suite and write SECURITY/attack_results.json under out_dir.
    Returns results list. timeout_s: max seconds per test_ref run (default 120).
    When llm_attacker=True, allow_network=True, and llm_backend set, runs LLM-attacker
    attacks (live LLM generates payloads); metadata will include llm_attacker_run and
    llm_attacker_model_ids when any such attack ran.
    When provider_id is set, use the registered security suite provider.
    """
    results = run_security_suite(
        policy_root=policy_root,
        repo_root=repo_root or policy_root,
        smoke_only=smoke_only,
        seed=seed,
        timeout_s=timeout_s,
        llm_attacker=llm_attacker,
        allow_network=allow_network,
        llm_backend=llm_backend,
        llm_model=llm_model,
        provider_id=provider_id,
        security_suite_path=security_suite_path,
    )
    security_dir = out_dir / "SECURITY"
    security_dir.mkdir(parents=True, exist_ok=True)
    write_attack_results(
        results,
        security_dir / "attack_results.json",
        metadata=metadata,
    )
    return results


_ensure_default_security_provider()
