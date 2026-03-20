#!/bin/bash
# RunPod boot entry point — called by all templates via container start command.
# Uploaded to /runpod-volume/shared/scripts/boot.sh
#
# Usage: Set TEMPLATE env var in RunPod template config.
#   TEMPLATE=quick    → Ollama + Open WebUI
#   TEMPLATE=research → vLLM + Jupyter
#   TEMPLATE=heavy    → Multi-GPU vLLM + Jupyter

SCRIPTS_DIR="/runpod-volume/shared/scripts"
source "${SCRIPTS_DIR}/common.sh"

TEMPLATE="${TEMPLATE:-quick}"
SESSION_ID="${TEMPLATE}-$(date +%Y%m%d-%H%M%S)"
export SESSION_ID SCRIPTS_DIR

# Persist logs to network volume
mkdir -p /runpod-volume/results/logs
exec > >(tee -a "/runpod-volume/results/logs/${SESSION_ID}.log") 2>&1

log "=== Boot: template=${TEMPLATE} session=${SESSION_ID} ==="

# Mark session start (used by session-end.sh)
touch /tmp/.session_start

# --- Setup phase (fail fast) ---
set -euo pipefail
validate_environment
setup_ssh
setup_environment

# --- Template-specific setup ---
if [ -f "${SCRIPTS_DIR}/templates/${TEMPLATE}.sh" ]; then
  log "Running ${TEMPLATE} template setup..."
  source "${SCRIPTS_DIR}/templates/${TEMPLATE}.sh"
else
  log "ERROR: Unknown template '${TEMPLATE}'. Available: quick, research, heavy"
  exit 1
fi

# --- Overlay (optional, runs after template) ---
if [ -n "${OVERLAY:-}" ] && [ -f "${SCRIPTS_DIR}/overlays/${OVERLAY}.sh" ]; then
  log "Applying overlay: ${OVERLAY}"
  source "${SCRIPTS_DIR}/overlays/${OVERLAY}.sh"
fi

# --- Background services (fail gracefully) ---
set +e
start_idle_watchdog
start_continuous_sync
set -e

# --- Signal-aware wait ---
trap 'log "Signal caught, shutting down..."; bash "${SCRIPTS_DIR}/session-end.sh"; kill 0; exit 0' SIGTERM SIGINT

log "=== Ready. Session: ${SESSION_ID} ==="
log "=== SSH tunnel in to access services ==="
tail -f /dev/null &
wait $!
