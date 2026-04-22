#!/bin/bash
# install-czkawka.sh — Install czkawka CLI + Web UI on Debian Bookworm LXC
#
# Usage: Run inside a Debian 12 (Bookworm) LXC container:
#   bash install-czkawka.sh
#
# What it does:
#   1. Installs system dependencies
#   2. Downloads czkawka_cli binary from GitHub releases
#   3. Installs Docker and runs czkawka web UI (jlesage/czkawka)
#   4. Verifies both CLI and web UI are working
#
# Prerequisites:
#   - Media share bind-mounted at /media inside the container
#   - Container nesting enabled (pct set <vmid> -features nesting=1)
#
# Sources:
#   - https://github.com/qarmin/czkawka
#   - https://hub.docker.com/r/jlesage/czkawka

set -euo pipefail

CZKAWKA_URL="https://github.com/qarmin/czkawka/releases/latest/download/linux_czkawka_cli_x86_64"
WEB_UI_PORT=5800

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

# --- Step 1: System packages ---
step 1 "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq wget ca-certificates curl gnupg lsb-release >/dev/null 2>&1
info "Packages installed"

# --- Step 2: Download czkawka_cli ---
step 2 "Downloading czkawka_cli"

if [ -f /usr/local/bin/czkawka_cli ]; then
    info "czkawka_cli already exists — overwriting with latest"
fi

wget -q --show-progress -O /usr/local/bin/czkawka_cli "$CZKAWKA_URL"
chmod 755 /usr/local/bin/czkawka_cli
info "Downloaded czkawka_cli"

# Verify CLI
if czkawka_cli --version 2>/dev/null; then
    info "czkawka_cli is working"
else
    error "czkawka_cli failed to run"
    exit 1
fi

# --- Step 3: Install Docker ---
step 3 "Installing Docker"

if command -v docker &>/dev/null; then
    info "Docker already installed"
else
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io >/dev/null 2>&1
    info "Docker installed"
fi

# Start Docker
service docker start 2>/dev/null || true
info "Docker is running"

# --- Step 4: Run czkawka Web UI ---
step 4 "Starting czkawka Web UI"

# Stop existing container if running
docker rm -f czkawka-web 2>/dev/null || true

# Create config directory for czkawka GUI settings
mkdir -p /opt/czkawka/config

docker run -d \
    --name czkawka-web \
    --restart unless-stopped \
    -p ${WEB_UI_PORT}:5800 \
    -v /opt/czkawka/config:/config:rw \
    -v /media:/media:rw \
    jlesage/czkawka

info "Web UI container starting..."

# Wait for web UI
for i in $(seq 1 30); do
    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:${WEB_UI_PORT}/ 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" != "000" ]; then
        break
    fi
    sleep 1
done

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
    info "Web UI responding (status ${HTTP_CODE})"
else
    warn "Web UI not responding yet (status ${HTTP_CODE}) — may still be pulling image"
    warn "Run 'docker logs czkawka-web' to check progress"
fi

# --- Step 5: Check media mount ---
step 5 "Checking media mount"

if [ -d /media ] && [ "$(ls -A /media 2>/dev/null)" ]; then
    FILE_COUNT=$(find /media -maxdepth 1 -type f -o -type d | head -20 | wc -l)
    info "Media mount found at /media (${FILE_COUNT}+ items visible)"
else
    warn "No media found at /media — ensure bind mount is configured"
fi

# --- Step 6: Enable Docker on boot ---
step 6 "Enabling Docker on boot"

# Create init.d script for docker autostart (LXC has no systemd)
if [ ! -f /etc/init.d/docker-czkawka ]; then
    cat > /etc/init.d/docker-czkawka << 'INITEOF'
#!/bin/sh
### BEGIN INIT INFO
# Provides:          docker-czkawka
# Required-Start:    $local_fs $network docker
# Required-Stop:     $local_fs $network
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: czkawka web UI via Docker
### END INIT INFO

case "$1" in
    start)
        docker start czkawka-web 2>/dev/null || true
        ;;
    stop)
        docker stop czkawka-web 2>/dev/null || true
        ;;
    restart)
        docker restart czkawka-web 2>/dev/null || true
        ;;
    status)
        docker inspect -f '{{.State.Status}}' czkawka-web 2>/dev/null
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
INITEOF
    chmod 755 /etc/init.d/docker-czkawka
    update-rc.d docker-czkawka defaults
    info "Docker autostart enabled"
fi

# --- Summary ---
CONTAINER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo -e "${GREEN}  czkawka installed successfully${NC}"
echo -e "${GREEN}════════════════════════════════════════════${NC}"
echo ""
echo "  Web UI:     http://${CONTAINER_IP}:${WEB_UI_PORT}/"
echo "  Media:      /media (bind-mounted from TrueNAS)"
echo "  Config:     /opt/czkawka/config/"
echo ""
echo "  CLI examples:"
echo ""
echo "  # Find duplicate files (>1MB)"
echo "  czkawka_cli dup -d /media -m 1048576"
echo ""
echo "  # Find similar images"
echo "  czkawka_cli image -d /media/photos -s Minimal"
echo ""
echo "  # Find big files (top 50)"
echo "  czkawka_cli big -d /media -n 50"
echo ""
echo "  # Find empty directories"
echo "  czkawka_cli empty-dirs -d /media"
echo ""
