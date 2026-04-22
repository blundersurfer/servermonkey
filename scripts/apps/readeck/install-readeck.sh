#!/bin/bash
# install-readeck.sh — Install Readeck read-it-later app on Debian LXC
#
# Usage: Run inside a fresh Debian Bookworm LXC container:
#   bash install-readeck.sh
#
# What it does:
#   1. Installs minimal dependencies (curl, ca-certificates)
#   2. Downloads latest Readeck binary for linux/amd64
#   3. Creates dedicated readeck user and data directory
#   4. Creates systemd service unit
#   5. Enables and starts Readeck on port 8000
#
# After running:
#   - Access Readeck at http://<container-ip>:8000
#   - Default admin account created on first visit
#
# Source: https://readeck.org/en/docs/

set -euo pipefail

# --- Configuration ---
READECK_VERSION="${READECK_VERSION:-latest}"
INSTALL_DIR="/opt/readeck"
DATA_DIR="/opt/readeck/data"
READECK_PORT="8000"
READECK_USER="readeck"

# --- Colors for output ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()  { echo -e "\n${GREEN}━━━ Step $1: $2 ━━━${NC}"; }

# --- Preflight checks ---
if [ "$(id -u)" -ne 0 ]; then
    error "Must run as root"
    exit 1
fi

if ! grep -qi 'debian' /etc/os-release 2>/dev/null; then
    warn "Expected Debian — detected: $(. /etc/os-release && echo "$PRETTY_NAME")"
fi

# --- Step 1: Install dependencies ---
step 1 "Installing minimal dependencies"
apt-get update -qq
apt-get install -y --no-install-recommends curl ca-certificates
apt-get clean
rm -rf /var/lib/apt/lists/*

# --- Step 2: Create readeck user and directories ---
step 2 "Creating readeck user and directories"
useradd --system --shell /usr/sbin/nologin --home-dir "$INSTALL_DIR" "$READECK_USER" 2>/dev/null || true
mkdir -p "$INSTALL_DIR" "$DATA_DIR"

# --- Step 3: Download Readeck binary ---
step 3 "Downloading Readeck binary"
READECK_DL_VERSION="0.22.2"
DOWNLOAD_URL="https://codeberg.org/readeck/readeck/releases/download/${READECK_DL_VERSION}/readeck-${READECK_DL_VERSION}-linux-amd64"
curl -fSL "$DOWNLOAD_URL" -o "$INSTALL_DIR/readeck"
chmod +x "$INSTALL_DIR/readeck"
info "Downloaded Readeck to $INSTALL_DIR/readeck"

# --- Step 4: Set ownership (config is auto-generated on first start) ---
step 4 "Setting ownership"
chown -R "$READECK_USER":"$READECK_USER" "$INSTALL_DIR"
info "Ownership set to $READECK_USER"

# --- Step 5: Create systemd service ---
step 5 "Creating systemd service"
cat > /etc/systemd/system/readeck.service <<'UNIT'
[Unit]
Description=Readeck read-it-later service
After=network.target

[Service]
Type=simple
User=readeck
Group=readeck
WorkingDirectory=/opt/readeck
ExecStart=/opt/readeck/readeck serve -config /opt/readeck/data/config.toml
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable readeck
info "Systemd service created and enabled"

# --- Step 6: Start Readeck ---
step 6 "Starting Readeck"
systemctl start readeck
sleep 2

# Verify it's running
if systemctl is-active --quiet readeck; then
    info "Readeck is running!"
else
    error "Readeck failed to start"
    systemctl status readeck --no-pager
    exit 1
fi

# --- Step 7: Bind to all interfaces (Readeck defaults to 127.0.0.1) ---
step 7 "Configuring network binding"
if grep -q 'host = "127.0.0.1"' "$DATA_DIR/config.toml" 2>/dev/null; then
    sed -i 's/host = "127.0.0.1"/host = "0.0.0.0"/' "$DATA_DIR/config.toml"
    systemctl restart readeck
    sleep 2
    info "Readeck now listening on 0.0.0.0:${READECK_PORT}"
fi

# --- Done ---
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Readeck installed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Access:  http://$(hostname -I | awk '{print $1}'):${READECK_PORT}"
echo "  Data:    ${DATA_DIR}"
echo "  Config:  ${DATA_DIR}/config.toml"
echo "  Service: systemctl {start|stop|restart|status} readeck"
echo ""
echo "  Create your admin account on first visit."
echo ""
