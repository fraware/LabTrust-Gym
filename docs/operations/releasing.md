# Releasing (PyPI and GitHub)

This document is the maintainer checklist for tagging a release. It complements the automated **Release** workflow (`.github/workflows/release.yml`).

## What the workflow does

On push of a tag matching `v*`:

1. **Build** — Copies `policy/` into `src/labtrust_gym/policy/`, runs `python -m build`, writes `release-assets/SHA256SUMS.txt` (hashes of wheel + sdist only), and `release-assets/policy-bundle-<tag>.tar.gz`.
2. **Publish** — Uploads **only** the contents of `dist/` (wheel + sdist) to PyPI using [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC). No long-lived PyPI token is required in the repo once PyPI is configured.
3. **GitHub Release** — Creates a release for the tag and attaches wheel, sdist, `SHA256SUMS.txt`, and the policy bundle tarball.
4. **Live LLM smoke** (optional) — Runs if `OPENAI_API_KEY` is set; failures do not block publish.

## PyPI Trusted Publishing setup

Configure the project on [PyPI](https://pypi.org/manage/project/labtrust-gym/settings/publishing/) (or TestPyPI first):

- **Publisher:** GitHub.
- **Repository:** `fraware/LabTrust-Gym` (or your public fork if different).
- **Workflow:** `Release` (file `.github/workflows/release.yml`).
- **Environment:** Leave blank unless you add a matching GitHub Environment (see below).

After the first successful OIDC publish, remove any legacy `TWINE_PASSWORD` / `PYPI_API_TOKEN` repository secrets used only for this workflow.

### Optional: GitHub Environment `pypi`

To require manual approval before PyPI upload, create an Environment named `pypi` in the repo settings and add protection rules. If you do, add to the `publish` job in `release.yml`:

```yaml
environment:
  name: pypi
  url: https://pypi.org/p/labtrust-gym
```

The name must match the environment configured on PyPI for the trusted publisher.

## Pre-flight checklist (before pushing the tag)

Do these in order; adjust if you use a release branch instead of `main`.

1. **Default branch CI** — Merge only when **CI** (`.github/workflows/ci.yml`) is green on the commit you will tag, including Windows if you claim Windows support.
2. **Version and release notes** — Bump `version` in `pyproject.toml`. Summarize user-facing changes in the GitHub Release (the workflow generates draft notes; edit or replace as needed).
3. **Dependency audit** — From a clean venv with the package installed (e.g. `pip install -e ".[dev]"`), run `pip install pip-audit` and `pip-audit`. Fix or document any findings. The repo also runs **audit-selfcheck** (`.github/workflows/audit-selfcheck.yml`) in CI. See [Dependency audit](ci.md#dependency-audit-optional) in the CI doc for environment tips.
4. **Security contacts** — Confirm [SECURITY.md](https://github.com/fraware/LabTrust-Gym/blob/main/SECURITY.md) points at the **public** repo (`fraware/LabTrust-Gym`) and the private advisory URL is correct.
5. **Docs and links** — README and `[project.urls]` in `pyproject.toml` should use the canonical documentation URL ([published site](https://fraware.github.io/LabTrust-Gym/)) and matching repository URL.
6. **Local install smoke** — Build locally (`python -m build`), create a fresh venv, `pip install dist/*.whl`, then `labtrust --version` and one fast path from the README (e.g. `labtrust quick-eval` with `[env,plots]` if needed).
7. **Trust verification (strongly recommended)** — For a `package-release` output, run `labtrust verify-release` with `--strict-fingerprints` as in [Trust verification](../risk-and-security/trust_verification.md).
8. **Tag** — `git tag -a vX.Y.Z -m "Release vX.Y.Z"` and `git push origin vX.Y.Z` (or push the tag from CI after merge, per team practice).

## After the tag

- Confirm the [PyPI project](https://pypi.org/project/labtrust-gym/) shows the new version.
- Confirm the [GitHub Release](https://github.com/fraware/LabTrust-Gym/releases) lists the expected assets (wheel, sdist, `SHA256SUMS.txt`, policy bundle).
- Smoke-install from PyPI: `pip install labtrust-gym[env,plots]==X.Y.Z` and `labtrust --version`.

## Optional: benchmark presentation bundle

If you are publishing benchmark narratives alongside the code release, see [Benchmark results pipeline](../benchmark_results_pipeline.md) for the `benchmark_suite.py publish` path.

## Recorded dependency audits (maintainer log)

Run `pip-audit` from a **fresh virtual environment** with only this project installed (see [Dependency audit](ci.md#dependency-audit-optional)); do not rely on a conda base or unrelated packages.

| Date (UTC) | Command / scope | Result |
|------------|-----------------|--------|
| 2026-04-05 | `pip install -e ".[dev,env,plots,llm_openai]"` then `pip-audit` | No known vulnerabilities in resolved dependencies; editable `labtrust-gym` skipped as expected. |
