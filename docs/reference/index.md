# Reference

Repository layout, lab profile, observability, and testing strategy.

**Documentation restructure:** Docs are organized into sections (getting-started, architecture, policy, coordination, benchmarks, contracts, risk-and-security, export, agents, operations, reference). Cross-doc links use paths relative to the docs root (e.g. `../operations/ci.md` from another section). If you find a broken link, update it to the path under the appropriate section. Set `strict: true` in `mkdocs.yml` once all links are updated.

| Document | Description |
|----------|-------------|
| [Repository structure](repository_structure.md) | Canonical layout and where to put outputs. |
| [Lab profile reference](lab_profile_reference.md) | Lab profile and provider IDs. |
| [Observability](observability.md) | Observability and logging. |
| [Online mode](online_mode.md) | Online mode and server. |
| [Testing strategy](testing_strategy.md) | Fuzz and metamorphic testing. |
