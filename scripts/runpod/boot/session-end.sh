#!/bin/bash
# Session cleanup — called by signal handler or idle watchdog.
# Uploaded to /runpod-volume/shared/scripts/session-end.sh

source "$(dirname "$0")/common.sh"

log "=== Session end: ${SESSION_ID:-unknown} ==="

# Save bash history for session review
cp ~/.bash_history "/runpod-volume/results/logs/${SESSION_ID:-unknown}_history.txt" 2>/dev/null

# Clean temporary model downloads (scratch space)
if [ -d /runpod-volume/models/downloads ]; then
  rm -rf /runpod-volume/models/downloads/*
  log "Cleaned temporary model downloads"
fi

log "=== Session end complete ==="
