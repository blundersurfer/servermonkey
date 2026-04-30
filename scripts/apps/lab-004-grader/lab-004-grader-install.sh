#!/bin/bash
# lab-004-grader-install.sh — Provision the H-COMPLEXITY pilot grader container
#
# Installs the toolchains the language-agnostic grader needs to compile + run
# candidate implementations across all 5 H-COMPLEXITY tiers:
#   ts-bun           → Bun runtime
#   python-stdlib    → python3 (stdlib http.server only)
#   java-jdk         → openjdk-17-jdk-headless
#   c-libmicrohttpd  → gcc + libmicrohttpd-dev
#   c-posix          → gcc only (POSIX sockets in libc)
#
# Also enables openssh-server with the shuri@nabu public key authorized for
# root login (key-only, no password) so coordinator sessions can shell in
# directly via Bash + ssh once the install completes.
#
# Idempotent: safe to re-run. apt-get install is no-op for existing packages;
# bun installer is no-op if Bun is already present and up-to-date; SSH key
# is appended only if not already in authorized_keys.
#
# Target environment: Ubuntu 24.04 LTS LXC container (vmid 511 on eshu).

set -euo pipefail

export DEBIAN_FRONTEND=noninteractive

# ─── Pubkey for SSH access ───
# This is the shuri@nabu key: ~/.ssh/shuri.pub on the coordinator machine.
# The MCP host must have read access to this file at install time, OR the
# key value below must be kept in sync if the user's shuri key rotates.
SHURI_PUBKEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIB4vd9kSxc8to0YWkOkulOVEM/cLamSLQuFxRZKCJI7d shuri@nabu"

echo "=== [1/6] apt update + base packages ==="
apt-get update -qq
apt-get install -y -qq \
    curl \
    ca-certificates \
    unzip \
    pkg-config \
    git \
    vim \
    less \
    net-tools \
    iproute2 \
    iputils-ping \
    dnsutils

echo "=== [2/6] grader toolchains ==="
apt-get install -y -qq \
    python3 \
    openjdk-17-jdk-headless \
    gcc \
    libmicrohttpd-dev

echo "=== [3/6] Bun (TS runtime) ==="
# Bun's installer drops the binary at /root/.bun/bin/bun and modifies
# ~/.bashrc — but ~/.bashrc isn't sourced under non-interactive bash
# (which is what `pct exec` and `ssh ... cmd` use). We therefore:
#   (a) export PATH inline so this script's verification step finds bun
#   (b) symlink /usr/local/bin/bun for future shells
#   (c) write a profile.d snippet so interactive shells get BUN_INSTALL
#       on the next login.
if ! [ -x /root/.bun/bin/bun ]; then
    curl -fsSL https://bun.sh/install | bash
fi
export BUN_INSTALL="/root/.bun"
export PATH="${BUN_INSTALL}/bin:${PATH}"
ln -sf /root/.bun/bin/bun /usr/local/bin/bun
cat > /etc/profile.d/bun.sh <<'PROFILE'
export BUN_INSTALL="/root/.bun"
export PATH="${BUN_INSTALL}/bin:${PATH}"
PROFILE
chmod +x /etc/profile.d/bun.sh
hash -r 2>/dev/null || true

echo "=== [4/6] openssh-server + key authorization ==="
apt-get install -y -qq openssh-server
systemctl enable ssh
systemctl start ssh

mkdir -p /root/.ssh
chmod 700 /root/.ssh
touch /root/.ssh/authorized_keys
chmod 600 /root/.ssh/authorized_keys

# Append shuri key only if not already present
if ! grep -qF "${SHURI_PUBKEY}" /root/.ssh/authorized_keys; then
    echo "${SHURI_PUBKEY}" >> /root/.ssh/authorized_keys
fi

# Harden sshd: disable password auth, allow only key-based root login
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PubkeyAuthentication.*/PubkeyAuthentication yes/' /etc/ssh/sshd_config

systemctl restart ssh

echo "=== [5/6] cleanup ==="
apt-get autoremove -y
apt-get clean

echo "=== [6/6] verification ==="
echo "--- python3 ---"
python3 --version
echo "--- javac ---"
javac --version
echo "--- java ---"
java --version
echo "--- gcc ---"
gcc --version | head -1
echo "--- libmicrohttpd ---"
pkg-config --modversion libmicrohttpd
echo "--- bun ---"
# Use full path explicitly to avoid PATH dependency in verification step
/root/.bun/bin/bun --version
echo "--- ssh ---"
systemctl is-active ssh

echo ""
echo "--- container ip ---"
ip -4 addr show eth0 | grep -oP '(?<=inet\s)\d+(\.\d+){3}' || true

echo ""
echo "--- disk usage ---"
df -h /

echo ""
echo "=== install complete ==="
