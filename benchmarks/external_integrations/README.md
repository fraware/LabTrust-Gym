# External integrations pin (LTG-PR7)

Frozen public-release identity for release-testing scripted, Gymnasium, PettingZoo, external Python, MARL, and verifier-optimization adapters.

- **Pin manifest:** [`pinned_release.v1.json`](pinned_release.v1.json)
- **Baselines pack:** [`../baselines_official/v0.2/`](../baselines_official/v0.2/) (canonical frozen baselines)
- **VA pack:** [`../verifier_assurance/release_packs/labtrust-va-release-v1/`](../verifier_assurance/release_packs/labtrust-va-release-v1/)

Gate tests: `tests/test_ltg_external_integrations.py`. Docs: [Scientific credibility](../../docs/benchmarks/scientific_credibility.md), [External integrations](../../docs/agents/external_integrations.md).

Default path is offline (no live proprietary LLM).
