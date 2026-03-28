#!/usr/bin/env bash
# =============================================================================
# Free / low-cost remote benchmark runner (Linux, NAS, cheap VM, homelab).
#
# Why: GitHub Actions costs money or minutes. This runs on ANY machine you keep
# awake (or a genuinely free-tier cloud VM) with SSH — your laptop can be off.
#
# FREE OR NEAR-ZERO HOST IDEAS (2025–2026 landscape; verify on provider sites):
#   • Oracle Cloud "Always Free" ARM (Ampere A1) — often $0 if you stay in tier.
#   • Hardware you already own: Raspberry Pi, NUC, old laptop, NAS with shell
#     (Synology/QNAP SSH, TrueNAS) — power cost only.
#   • Home LAN: leave a small box on 24/7; connect with SSH from anywhere via
#     Tailscale or WireGuard (Tailscale free tier for personal use).
#
# NOT "free forever": AWS/GCP/Azure trial credits, Fly.io free allowance — OK
# for experiments but they expire or cap.
#
# USAGE (on the remote host, after git clone + venv + pip install -e ".[...]"):
#   export PRIME_INTELLECT_API_KEY=...   # or PRIME_API_KEY
#   cd LabTrust-Gym
#   chmod +x scripts/run_prime_live_nohup.sh
#   ./scripts/run_prime_live_nohup.sh --episodes 1 --out-dir runs/pi_remote \
#       --methods llm_auction_bidder
#
# Logs: runs/background_logs/prime_live_<UTC>_<pid>.log
# PID:  runs/background_logs/latest_prime_nohup.pid
#
# Optional: tmux so you can attach and watch live:
#   tmux new -s labtrust
#   ./scripts/run_prime_live_nohup.sh ...   # or run python directly in foreground
#   # detach: Ctrl-B D  —  reattach: tmux attach -t labtrust
#
# =============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGDIR="${ROOT}/runs/background_logs"
mkdir -p "${LOGDIR}"

if ! command -v python3 >/dev/null 2>&1 && ! command -v python >/dev/null 2>&1; then
  echo "error: need python3 or python on PATH" >&2
  exit 1
fi
PY="$(command -v python3 2>/dev/null || command -v python)"

STAMP="$(date -u +"%Y%m%d_%H%M%S")"
LOG="${LOGDIR}/prime_live_${STAMP}.log"
PIDFILE="${LOGDIR}/latest_prime_nohup.pid"
META="${LOGDIR}/latest_prime_nohup.json"

cd "${ROOT}"

# Redirect both stdout and stderr to the log file.
nohup "${PY}" scripts/run_all_methods_prime_live_full.py "$@" >>"${LOG}" 2>&1 &
CHILD_PID=$!

echo "${CHILD_PID}" >"${PIDFILE}"
printf '{"pid":%s,"log":"%s","started_utc":"%s","cwd":"%s"}\n' \
  "${CHILD_PID}" "${LOG}" "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "${ROOT}" >"${META}"

echo "Detached Prime live run started."
echo "  PID     ${CHILD_PID}"
echo "  log     ${LOG}"
echo "  meta    ${META}"
echo ""
echo "Tail:    tail -f '${LOG}'"
echo "Stop:    kill ${CHILD_PID}"
