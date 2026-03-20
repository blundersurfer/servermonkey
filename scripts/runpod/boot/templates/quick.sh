#!/bin/bash
# Quick template: Ollama + Open WebUI
# Base image: ollama/ollama:latest (Alpine-based, no Python)
# GPU: RTX 4090 (spot)
# SSH tunnel: -L 8080:localhost:8080 -L 11434:localhost:11434

log "=== Quick template ==="

# Ollama stores models in its own format (manifests + blobs).
# OLLAMA_MODELS on the network volume = models persist across pod lifecycles.
export OLLAMA_MODELS="/runpod-volume/models/ollama"
export OLLAMA_HOST="127.0.0.1:11434"
mkdir -p "$OLLAMA_MODELS"

log "Starting Ollama (127.0.0.1:11434)..."
ollama serve &
sleep 3

log "Available models:"
ollama list

# Open WebUI — install Python + pip on Alpine if needed
if ! command -v pip &>/dev/null; then
  if command -v apk &>/dev/null; then
    log "Installing Python on Alpine for Open WebUI..."
    apk add --no-cache python3 py3-pip 2>/dev/null
  fi
fi

if command -v pip &>/dev/null; then
  # Use a persistent install directory on the volume
  export DATA_DIR="/runpod-volume/shared/.open-webui"
  mkdir -p "$DATA_DIR"

  if ! command -v open-webui &>/dev/null; then
    log "Installing Open WebUI (first run — may take 1-2 min)..."
    pip install -q open-webui 2>/dev/null || pip3 install -q open-webui 2>/dev/null
  fi

  if command -v open-webui &>/dev/null; then
    log "Starting Open WebUI on 127.0.0.1:8080..."
    open-webui serve --host 127.0.0.1 --port 8080 &
  else
    log "WARNING: Open WebUI install failed. Use Ollama API directly."
  fi
else
  log "WARNING: Python not available — skipping Open WebUI. Use Ollama API directly."
fi

log "Ready: Ollama :11434, WebUI :8080 (if installed)"
log "SSH tunnel: ssh -L 8080:localhost:8080 -L 11434:localhost:11434 root@<ip> -p <port>"
