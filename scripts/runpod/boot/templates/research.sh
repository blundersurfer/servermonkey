#!/bin/bash
# Research template: vLLM + Jupyter Lab
# Base image: runpod/pytorch (Ubuntu, Python pre-installed)
# GPU: L40S (spot) or A100 80GB (on-demand)
# SSH tunnel: -L 8888:localhost:8888 -L 8000:localhost:8000

log "=== Research template ==="

# GPU health check (pytorch image has torch)
check_gpu

# Persistent venv on network volume (survives pod restarts)
activate_venv

# vLLM + Jupyter — installed to persistent venv
setup_vllm_jupyter

# Activity log for session tracking (coding assistant edits, commands, results)
export SESSION_LOG="/runpod-volume/results/logs/${SESSION_ID}_activity.log"
touch "$SESSION_LOG"
log "Activity log: $SESSION_LOG"

# OpenCode available on-demand — not installed at boot.
# When needed during a session:
#   export OPENAI_API_BASE="http://127.0.0.1:8000/v1"
#   export OPENAI_API_KEY="not-needed"
#   # Download OpenCode binary or install, then run:
#   opencode

log "Ready: vLLM :8000, Jupyter :8888"
log "SSH tunnel: ssh -L 8888:localhost:8888 -L 8000:localhost:8000 root@<ip> -p <port>"
