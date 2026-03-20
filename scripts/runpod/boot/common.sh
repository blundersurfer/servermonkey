#!/bin/bash
# RunPod boot scripts — shared functions
# Uploaded to /runpod-volume/shared/scripts/common.sh

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

validate_environment() {
  # RunPod API key is NOT on the pod. It lives in the local machine's
  # libsecret keyring and is used by runpod.py CLI only.
  # The pod uses runpodctl (pre-installed) for self-termination.
  if ! command -v runpodctl &>/dev/null; then
    log "WARNING: runpodctl not found — idle watchdog cannot self-terminate"
  fi
  log "Environment validated"
}

setup_ssh() {
  if ! command -v sshd &>/dev/null; then
    if command -v apk &>/dev/null; then
      apk add --no-cache openssh-server 2>/dev/null
    elif command -v apt-get &>/dev/null; then
      apt-get update -qq && apt-get install -y -qq openssh-server
    else
      log "WARNING: Cannot install SSH — unknown package manager"
      return 1
    fi
  fi

  mkdir -p /var/run/sshd
  # Harden SSH: key-only auth, no passwords
  sed -i 's/#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
  sed -i 's/#*PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config

  if [ -n "${PUBLIC_KEY:-}" ]; then
    mkdir -p /root/.ssh
    echo "$PUBLIC_KEY" > /root/.ssh/authorized_keys
    chmod 700 /root/.ssh && chmod 600 /root/.ssh/authorized_keys
  fi

  /usr/sbin/sshd
  log "SSH started (key-only auth)"
}

setup_environment() {
  # Write RunPod env vars to profile (overwrite, not append)
  # grep may return 1 if no RUNPOD_ vars exist — don't fail under pipefail
  env | grep '^RUNPOD_' > /tmp/.runpod_env 2>/dev/null || true
  if [ -s /tmp/.runpod_env ]; then
    while IFS='=' read -r k v; do
      echo "export ${k}=\"${v}\""
    done < /tmp/.runpod_env > /etc/profile.d/runpod.sh 2>/dev/null
    chmod 644 /etc/profile.d/runpod.sh 2>/dev/null
  fi
  rm -f /tmp/.runpod_env

  export PIP_CACHE_DIR="/runpod-volume/shared/.pip-cache"
  mkdir -p "$PIP_CACHE_DIR"

  export HF_HOME="/runpod-volume/shared/.hf-cache"
  mkdir -p "$HF_HOME"

  log "Environment configured"
}

check_gpu() {
  nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | while read -r l; do
    log "GPU: $l"
  done
  python3 -c "import torch; torch.randn(100,100).cuda(); print('GPU OK')" 2>/dev/null \
    || log "WARNING: GPU compute test failed (torch not available or GPU issue)"
}

activate_venv() {
  local venv="/runpod-volume/shared/.venvs/${TEMPLATE}"
  if [ ! -d "$venv" ]; then
    log "Creating persistent venv for ${TEMPLATE}..."
    python3 -m venv "$venv" --system-site-packages
  fi
  source "$venv/bin/activate"
  log "Venv active: $venv"
}

install_if_missing() {
  local pkg="$1"
  if pip show "$pkg" &>/dev/null; then
    log "$pkg: cached"
  else
    log "Installing $pkg..."
    pip install -q "$pkg"
  fi
}

setup_vllm_jupyter() {
  install_if_missing "vllm"
  install_if_missing "jupyterlab"

  local model="${MODEL:-/runpod-volume/models/vllm/qwen3-32b}"
  local tp="${TP_SIZE:-1}"

  if [ -d "$model" ]; then
    log "Starting vLLM (model=$model, tp=$tp)..."
    python -m vllm.entrypoints.openai.api_server \
      --model "$model" \
      --host 127.0.0.1 \
      --port 8000 \
      --tensor-parallel-size "$tp" \
      --gpu-memory-utilization 0.85 &
  else
    log "WARNING: Model not found at $model — start vLLM manually."
  fi

  log "Starting Jupyter Lab on 127.0.0.1:8888..."
  jupyter lab \
    --ip=127.0.0.1 \
    --port=8888 \
    --no-browser \
    --allow-root \
    --NotebookApp.token='' \
    --notebook-dir=/runpod-volume/results &

  log "Jupyter :8888, vLLM :8000"
}

start_idle_watchdog() {
  local max_hours="${MAX_HOURS:-4}"
  local timeout=$((max_hours * 3600))
  local scripts_dir="${SCRIPTS_DIR}"

  (
    idle_since=$(date +%s)
    while true; do
      sleep 300
      gpu=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1)
      if [ "${gpu:-0}" -gt 5 ]; then
        idle_since=$(date +%s)
      fi
      elapsed=$(( $(date +%s) - idle_since ))
      if [ "$elapsed" -ge "$timeout" ]; then
        log "IDLE TIMEOUT: No GPU activity for ${max_hours}h"
        bash "${scripts_dir}/session-end.sh"
        # runpodctl is pre-installed on RunPod pods and uses pod identity
        # — no API key needed on the pod
        runpodctl stop pod 2>/dev/null || log "WARNING: runpodctl stop failed"
        exit 0
      fi
    done
  ) &

  log "Idle watchdog started (${max_hours}h, GPU-utilization-based)"
}

start_continuous_sync() {
  local backup_target="${BACKUP_S3_ENDPOINT:-}"
  local backup_bucket="${BACKUP_S3_BUCKET:-research-backup}"

  if [ -z "$backup_target" ]; then
    log "No BACKUP_S3_ENDPOINT set — continuous sync disabled"
    return
  fi

  (
    while true; do
      sleep 300
      aws s3 sync /runpod-volume/results/ "s3://${backup_bucket}/results/" \
        --endpoint-url "$backup_target" \
        --exclude "*.bin" \
        --exclude "*.safetensors" \
        --exclude "*.gguf" \
        --quiet 2>/dev/null
    done
  ) &

  log "Continuous sync active (every 5min → ${backup_target})"
}
