# Reproducible Builds

This document describes how to build the LabTrust-Gym wheel and sdist in a reproducible way for supply-chain attestation (SLSA-ish guarantees). Outputs are deterministic where feasible; environment pinning is recommended for full reproducibility.

## Goals

- **Deterministic artifacts**: Same source and environment produce identical wheel/sdist hashes where possible.
- **Dependency inventory**: Runtime and policy deps are recorded in SECURITY/deps_inventory_runtime.json and deps_inventory.json.
- **Offline-friendly**: Deterministic backends do not require network; build can be run in isolated environments.

## Environment Pinning

For best reproducibility:

1. **Python version**: Pin to the same minor version used in CI (e.g. 3.11). Use `pyenv`, `conda`, or a dedicated venv with a fixed interpreter.
2. **Build tools**: Pin `setuptools` and `wheel` versions in a constraints file or install from a lockfile.
3. **SOURCEDATE_EPOCH**: Set to a fixed timestamp (e.g. last release date) so source date is deterministic (affects ZIP metadata when supported by the toolchain).
4. **Platform**: Build on a single OS/arch for a given release (e.g. Linux x86_64 for PyPI); cross-platform wheels require one build per platform.

Example (Unix):

```bash
export SOURCEDATE_EPOCH=$(date -d "2025-01-01" +%s)
pip install --constraint constraints.txt build
python -m build
```

## Exact Build Steps

1. **Clone and enter repo** (clean tree, no uncommitted changes for release):

   ```bash
   git clone <repo-url> labtrust-gym && cd labtrust-gym
   git checkout vX.Y.Z
   ```

2. **Create a clean virtual environment**:

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   ```

3. **Install build dependencies** (optionally from constraints):

   ```bash
   pip install --upgrade pip setuptools wheel
   pip install build
   ```

4. **Copy policy into package** (matches CI and wheel layout):

   ```bash
   mkdir -p src/labtrust_gym/policy
   cp -r policy/* src/labtrust_gym/policy/
   ```

5. **Build wheel and sdist**:

   ```bash
   python -m build
   ```

6. **Generate checksums** (for attestation):

   ```bash
   cd dist
   sha256sum *.whl *.tar.gz > SHA256SUMS.txt
   cd ..
   ```

7. **Verify**: Compare `dist/SHA256SUMS.txt` with the hashes published in the release.

## Script

`scripts/build_repro.sh` automates the above in a clean venv and prints SHA256 hashes of the built artifacts. Run from the repository root:

```bash
./scripts/build_repro.sh
```

On Windows, use Git Bash or WSL, or run the equivalent steps in PowerShell (see script comments for manual steps).

## Release Attestation

- **CI**: The Release workflow (`.github/workflows/release.yml`) builds wheel and sdist, generates `dist/SHA256SUMS.txt`, and uploads the `dist/` directory as an artifact. Downstream consumers can verify hashes against this file.
- **Package release artifact**: `labtrust package-release --profile paper_v0.1 --out <dir>` includes SECURITY/deps_inventory_runtime.json and SECURITY/deps_inventory.json; the release manifest (MANIFEST.v0.1.json) contains per-file SHA256 for the whole artifact.

## Limitations

- **ZIP non-determinism**: Some Python versions or tools may write non-deterministic timestamps or ordering into wheels; SOURCEDATE_EPOCH and pinned build tools mitigate this where supported.
- **Policy copy**: The in-repo `policy/` is copied into `src/labtrust_gym/policy/` before build; ensure the tree is clean so the copied policy matches the tag.
