#!/bin/bash
# Heavy template: Multi-GPU vLLM + Jupyter Lab
# Base image: runpod/pytorch (Ubuntu, Python pre-installed)
# GPU: 2-4× A100 SXM (spot)
# SSH tunnel: -L 8888:localhost:8888 -L 8000:localhost:8000

log "=== Heavy template ==="

# Auto-detect GPU count for tensor parallelism
export TP_SIZE=$(nvidia-smi -L 2>/dev/null | wc -l)
log "GPUs detected: ${TP_SIZE}"

# GPU health check
check_gpu

# Persistent venv
activate_venv

# DeepSpeed for multi-GPU training workloads
install_if_missing "deepspeed"

# vLLM + Jupyter — TP_SIZE is picked up by setup_vllm_jupyter
setup_vllm_jupyter

log "Ready: ${TP_SIZE}× GPU, vLLM :8000 (tp=${TP_SIZE}), Jupyter :8888"
log "SSH tunnel: ssh -L 8888:localhost:8888 -L 8000:localhost:8000 root@<ip> -p <port>"
