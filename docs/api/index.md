# API Reference

Auto-generated from docstrings (mkdocstrings). Build the docs site with `pip install -e ".[docs]"` and `mkdocs build --strict`.

- **Engine, policy, benchmarks, studies**: Core env, loader/validate, runner/tasks, study_runner, **coordination_scale**, **coordination_study_runner**, **security_runner**, **securitization**, **official_pack**, reproduce. Safety case generation: `labtrust_gym.security.safety_case` (emit_safety_case).
- **Errors and config**: `labtrust_gym.errors` (LabTrustError, PolicyLoadError, PolicyPathError); `labtrust_gym.config` (get_repo_root, policy_path, get_policy_dir). Policy path resolution raises PolicyPathError when the policy directory is not found or LABTRUST_POLICY_DIR is invalid; see [Installation](../getting-started/installation.md) and [Troubleshooting](../getting-started/troubleshooting.md#policy-directory-not-found-policypatherror).
- **LLM baselines**: `labtrust_gym.baselines.llm` (agent, backends deterministic/openai_live/ollama_live, signing proxy, parse utilities); see [LLM baselines](../agents/llm_baselines.md) and [Live LLM](../agents/llm_live.md).
- **Coordination**: Scale generation and study runner; methods and kernel live under `labtrust_gym.baselines.coordination`; see [Coordination methods](../coordination/coordination_methods.md) and [Coordination studies](../coordination/coordination_studies.md).

## Engine

::: labtrust_gym.engine.core_env.CoreEnv
    options:
      show_root_heading: true
      members_order: source

## Policy

::: labtrust_gym.policy.loader
    options:
      show_root_heading: true
      members_order: source

::: labtrust_gym.policy.validate
    options:
      show_root_heading: true
      members_order: source

## Benchmarks

::: labtrust_gym.benchmarks.runner
    options:
      show_root_heading: true
      members_order: source

::: labtrust_gym.benchmarks.tasks
    options:
      show_root_heading: true
      members_order: source

::: labtrust_gym.benchmarks.coordination_scale
    options:
      show_root_heading: true
      members_order: source

## Studies

::: labtrust_gym.studies.study_runner
    options:
      show_root_heading: true
      members_order: source

::: labtrust_gym.studies.reproduce
    options:
      show_root_heading: true
      members_order: source

::: labtrust_gym.studies.coordination_study_runner
    options:
      show_root_heading: true
      members_order: source

## Runner and adapter

::: labtrust_gym.runner.adapter.LabTrustEnvAdapter
    options:
      show_root_heading: true
      members_order: source

::: labtrust_gym.runner.golden_runner
    options:
      show_root_heading: true
      members_order: source

## Export

::: labtrust_gym.export.ui_export
    options:
      show_root_heading: true
      members_order: source

## Envs (PettingZoo wrappers)

::: labtrust_gym.envs.pz_parallel.LabTrustParallelEnv
    options:
      show_root_heading: true
      members_order: source
