#!/bin/bash
# install-kiwix.sh — Install Kiwix server for offline Wikipedia on Debian LXC
#
# Usage: Run inside a Debian LXC container (same container as Wiki.js):
#   bash install-kiwix.sh
#
# What it does:
#   1. Installs kiwix-tools (kiwix-serve binary)
#   2. Creates ZIM library directory at /opt/kiwix/library
#   3. Creates systemd service for kiwix-serve on port 8080
#   4. Provides download commands for Wikipedia ZIM files
#
# After running:
#   - Download ZIM files to /opt/kiwix/library/
#   - Start/restart the kiwix service
#   - Access at http://<container-ip>:8080
#
# Prerequisites:
#   - Container bootstrapped with systemd (entrypoint removed)
#
# Source: https://kiwix.org

set -euo pipefail

# --- Configuration ---
KIWIX_DIR="/opt/kiwix"
KIWIX_PORT=8080

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

# --- Step 1: Install kiwix-tools ---
step 1 "Installing kiwix-tools"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends kiwix-tools ca-certificates wget >/dev/null 2>&1

if command -v kiwix-serve &>/dev/null; then
    info "kiwix-serve installed: $(kiwix-serve --version 2>&1 | head -1)"
else
    error "kiwix-serve not found after install"
    exit 1
fi

# --- Step 2: Create library directory ---
step 2 "Creating library directory"
mkdir -p "$KIWIX_DIR/library"
useradd --system --shell /usr/sbin/nologin --home-dir "$KIWIX_DIR" kiwix 2>/dev/null || true
chown -R kiwix:kiwix "$KIWIX_DIR"
info "Library directory: $KIWIX_DIR/library"

# --- Step 3: Create launcher script ---
step 3 "Creating launcher script"

# kiwix-serve needs explicit file paths (no glob in systemd ExecStart)
cat > /usr/local/bin/kiwix-start.sh << 'LAUNCHER'
#!/bin/bash
# Launcher for kiwix-serve — finds all .zim files and serves them
ZIM_DIR="/opt/kiwix/library"
ZIM_FILES=$(find "$ZIM_DIR" -name "*.zim" -type f 2>/dev/null | tr '\n' ' ')

if [ -z "$ZIM_FILES" ]; then
    echo "No ZIM files found in $ZIM_DIR"
    echo "Download ZIM files first — see install instructions."
    # Keep running so systemd doesn't restart-loop
    sleep infinity
fi

exec /usr/bin/kiwix-serve --port 8080 --address 0.0.0.0 $ZIM_FILES
LAUNCHER
chmod 755 /usr/local/bin/kiwix-start.sh
info "Launcher script created"

# --- Step 4: Create systemd service ---
step 4 "Creating systemd service"
cat > /etc/systemd/system/kiwix.service << 'UNIT'
[Unit]
Description=Kiwix Server — Offline Wikipedia
After=network.target

[Service]
Type=simple
User=kiwix
Group=kiwix
ExecStart=/usr/local/bin/kiwix-start.sh
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable kiwix
info "Systemd service created and enabled"

# --- Summary ---
CONTAINER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Kiwix server installed!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Port:      ${KIWIX_PORT}"
echo "  Library:   ${KIWIX_DIR}/library/"
echo "  Service:   systemctl {start|stop|restart|status} kiwix"
echo ""
echo -e "  ${YELLOW}━━━ Download Wikipedia ZIM files ━━━${NC}"
echo ""
echo "  Browse all available ZIM files at:"
echo "  https://download.kiwix.org/zim/wikipedia/"
echo ""
echo "  # English Wikipedia — text only (~7 GB, fastest download):"
echo "  cd ${KIWIX_DIR}/library"
echo "  wget https://download.kiwix.org/zim/wikipedia_en_all_nopic.zim"
echo ""
echo "  # English Wikipedia — with images (~100 GB, full clone):"
echo "  cd ${KIWIX_DIR}/library"
echo "  wget https://download.kiwix.org/zim/wikipedia_en_all_maxi.zim"
echo ""
echo "  # Other useful ZIM files:"
echo "  # - wikipedia_en_all_mini.zim  (~12 GB, compressed articles)"
echo "  # - wiktionary_en_all.zim      (English dictionary)"
echo "  # - stackexchange.zim          (StackOverflow archive)"
echo ""
echo "  After downloading, fix ownership and start:"
echo "  chown -R kiwix:kiwix ${KIWIX_DIR}/library"
echo "  systemctl restart kiwix"
echo ""
echo "  Access at: http://${CONTAINER_IP}:${KIWIX_PORT}"
echo ""
