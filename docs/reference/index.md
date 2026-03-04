# Reference

Repository layout, lab profile, observability, and testing strategy.

**Documentation restructure:** Docs are organized into sections (getting-started, architecture, policy, coordination, benchmarks, contracts, risk-and-security, export, agents, operations, reference). Cross-doc links use paths relative to the docs root (e.g. `../operations/ci.md` from another section). If you find a broken link, update it to the path under the appropriate section. Set `strict: true` in `mkdocs.yml` once all links are updated.

| Document | Description |
|----------|-------------|
| [Glossary](glossary.md) | Definitions of terms (e.g. official baselines vs coordination method) to avoid ambiguity. |
| [Repository structure](repository_structure.md) | Canonical layout and where to put outputs. |
| [State of the art and limits](state_of_the_art_and_limits.md) | What is SOTA, deployment ready, and reusable; coordination definition of done, rate limiter, debate, vectorized envs. |
| [Episode viewer](episode_viewer.md) | Episode simulation viewer: data sources, bundle build, lab design, views. |
| [Outputs and results](outputs_and_results.md) | Where CLI and CI write results, schemas, and quick reference. |
| [Lab profile reference](lab_profile_reference.md) | Lab profile and provider IDs. |
| [Observability](observability.md) | Observability and logging. |
| [Online mode](online_mode.md) | Online mode and server. |
| [Testing strategy](testing_strategy.md) | Fuzz and metamorphic testing. |
