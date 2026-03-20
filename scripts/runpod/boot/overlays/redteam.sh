#!/bin/bash
# Red Team overlay — applied after base template setup.
# Adds offensive security agent with web search and dual-model support.
#
# Requires: base template with vLLM (research or heavy). Warns on quick.
# Usage: Set OVERLAY=redteam in RunPod env alongside TEMPLATE=research.

OVERLAY_DIR="${SCRIPTS_DIR}/overlays/redteam"

# --- Sanity check ---
if [ "${TEMPLATE}" = "quick" ]; then
  log "WARNING: redteam overlay expects vLLM (research/heavy template)."
  log "  quick template uses Ollama — agent.py will not work."
fi

# --- Install agent dependencies ---
log "Installing red team agent dependencies..."
install_if_missing "openai"
install_if_missing "duckduckgo-search"

# --- Start planner model (dual-model support) ---
PLANNER_MODEL="${PLANNER_MODEL:-/runpod-volume/models/vllm/deepseek-r1-distill-qwen3-8b}"
if [ -d "$PLANNER_MODEL" ]; then
  log "Starting planner vLLM on 127.0.0.1:8001..."
  python -m vllm.entrypoints.openai.api_server \
    --model "$PLANNER_MODEL" \
    --host 127.0.0.1 \
    --port 8001 \
    --gpu-memory-utilization 0.10 &
  log "Planner model starting on :8001 (DeepSeek-R1-Distill)"
else
  log "No planner model at ${PLANNER_MODEL} — plan mode will fall back to executor model."
fi

# --- Usage instructions ---
log "=== Red Team Overlay Active ==="
log "  Agent:    python ${OVERLAY_DIR}/agent.py"
log "  Plan:     python ${OVERLAY_DIR}/agent.py --mode plan"
log "  Execute:  python ${OVERLAY_DIR}/agent.py --mode exec"
log "  Prompts:  python ${OVERLAY_DIR}/agent.py --list-prompts"
log "  Load:     python ${OVERLAY_DIR}/agent.py --prompt recon"
