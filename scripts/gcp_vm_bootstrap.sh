#!/usr/bin/env bash
# Bootstrap LabTrust-Gym on a fresh Ubuntu VM (e.g. GCP Compute Engine, Ubuntu 24.04).
#
# Usage:
#   ./scripts/gcp_vm_bootstrap.sh <git-repo-url> [branch]
#
# Example:
#   ./scripts/gcp_vm_bootstrap.sh https://github.com/you/LabTrust-Gym.git main
#
# Requires: sudo apt, git. Clones into $HOME/LabTrust-Gym (existing dir must be moved aside).
set -euo pipefail

REPO_URL="${1:-}"
BRANCH="${2:-main}"

if [[ -z "${REPO_URL}" ]]; then
  echo "Usage: $0 <git-repo-url> [branch]" >&2
  exit 1
fi

TARGET="${HOME}/LabTrust-Gym"

if [[ -d "${TARGET}" ]]; then
  echo "error: ${TARGET} already exists; move or remove it first." >&2
  exit 1
fi

sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip build-essential

git clone --branch "${BRANCH}" --depth 1 "${REPO_URL}" "${TARGET}"
cd "${TARGET}"
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -U pip
pip install -e ".[dev,env,plots,llm_prime_intellect]"

echo ""
echo "Done. Next on this VM:"
echo "  source ${TARGET}/.venv/bin/activate"
echo "  export PRIME_INTELLECT_API_KEY=...   # or: source ~/prime.env"
echo "  cd ${TARGET}"
echo "  ./scripts/run_prime_live_nohup.sh --out-dir runs/gcp_prime --episodes 1 --methods llm_auction_bidder"
echo ""
echo "See docs/benchmarks/gcp_prime_runner.md for the full GCP runbook."
