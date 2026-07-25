# External integrations (LTG-PR7)

Release-test gate for adapters that external researchers use against a **pinned public release**. Default path is offline: no live proprietary LLM.

## Pinned release

Identity lives in [`benchmarks/external_integrations/pinned_release.v1.json`](../../benchmarks/external_integrations/pinned_release.v1.json).

| Field | Binding |
|-------|---------|
| Baselines pack | `benchmarks/baselines_official/v0.2` (`throughput_sla` / `scripted_ops_v1` / seed `123` / timing `explicit`) |
| Policy fingerprint | Digested in pin + `metadata.json` (must match) |
| Git SHA prefix | From frozen baselines metadata |
| VA pack | `benchmarks/verifier_assurance/release_packs/labtrust-va-release-v1` (VA-13 reconstruct) |

Loader: `labtrust_gym.benchmarks.external_integrations.load_pinned_release`.

## Integrations under test

| # | Integration | How exercised | Extras |
|---|-------------|----------------|--------|
| 1 | Native scripted agent | `run_benchmark` on pin task/seed + EvidenceBundle verify | — (needs `[env]` for PZ env) |
| 2 | Gymnasium wrapper | `LabTrustGymnasiumWrapper` reset/step with pin seed | `[env]` |
| 3 | PettingZoo wrapper | `LabTrustParallelEnv` reset/step with pin seed | `[env]` |
| 4 | External Python agent | `labtrust eval-agent` / `examples.external_agent_demo:SafeNoOpAgent` | `[env]` |
| 5 | MARL baseline | `train-ppo` / `eval-ppo` smoke timesteps | `[marl]` (skip if missing) |
| 6 | Verifier optimization | VA-13 offline `numpy_ppo` vs `V_public` + VA pack reconstruct | none (CI-safe) |

Where applicable, each path writes a minimal EvidenceBundle bound to the pin's `policy_fingerprint` and runs `verify_bundle` (LTG-PR6 reconstruction digests).

## Commands

```bash
# Default CI path (skips MARL when [marl] not installed; skips env wrappers when [env] missing)
pytest tests/test_ltg_external_integrations.py -v

# Full six integrations when extras present
pip install -e ".[dev,env,marl]"
pytest tests/test_ltg_external_integrations.py -v
```

External agent smoke (same pin task/seed):

```bash
labtrust eval-agent --agent "examples.external_agent_demo:SafeNoOpAgent" \
  --task throughput_sla --episodes 1 --seed 123 --out out.json
```

## Non-claims

Passing this gate shows adapters run against the documented frozen pack identity and produce reconstructable evidence where wired. It does **not** claim clinical validation, deployment readiness, or full official-baseline metric regression (that remains `LABTRUST_CHECK_BASELINES=1`).

See also: [Scientific credibility](../benchmarks/scientific_credibility.md), [Scripted baselines](scripted_baselines.md), [MARL baselines](marl_baselines.md), [PettingZoo API](pettingzoo_api.md).
