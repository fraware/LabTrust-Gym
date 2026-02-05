#!/usr/bin/env bash
# Reproducible build: clean venv, copy policy, build wheel+sdist, print SHA256.
# Run from repo root. Usage: ./scripts/build_repro.sh
# On Windows: use Git Bash or WSL, or run equivalent steps in PowerShell (see docs/reproducible_builds.md).

set -e
REPO_ROOT="${REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$REPO_ROOT"

VENV_DIR="${VENV_DIR:-$REPO_ROOT/.venv_build}"
rm -rf "$VENV_DIR"
echo "=== Creating clean venv at $VENV_DIR ==="
python3 -m venv "$VENV_DIR"
# shellcheck source=/dev/null
source "$VENV_DIR/bin/activate"

echo "=== Installing build deps ==="
pip install --upgrade pip setuptools wheel -q
pip install build -q

echo "=== Copying policy into package (match CI) ==="
mkdir -p src/labtrust_gym/policy
cp -r policy/* src/labtrust_gym/policy/

echo "=== Building wheel and sdist ==="
python -m build --outdir dist

echo "=== SHA256 of artifacts ==="
if command -v sha256sum >/dev/null 2>&1; then
  (cd dist && sha256sum *.whl *.tar.gz 2>/dev/null || true) | tee dist/SHA256SUMS.txt
elif command -v shasum >/dev/null 2>&1; then
  (cd dist && shasum -a 256 *.whl *.tar.gz 2>/dev/null || true) | tee dist/SHA256SUMS.txt
else
  echo "No sha256sum/shasum found; write SHA256SUMS.txt manually."
fi

echo "=== Done. Artifacts in dist/ ==="
ls -la dist/
