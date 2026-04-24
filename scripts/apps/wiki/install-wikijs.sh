#!/bin/bash
# install-wikijs.sh — Install Wiki.js personal wiki on Debian Bookworm LXC
#
# Usage: Run inside a Debian 12 (Bookworm) LXC container:
#   bash install-wikijs.sh
#
# What it does:
#   1. Installs Node.js 18 LTS via NodeSource
#   2. Installs PostgreSQL and creates wiki database
#   3. Downloads Wiki.js v2.5.304
#   4. Configures Wiki.js with PostgreSQL backend
#   5. Creates systemd service on port 3000
#   6. Starts Wiki.js
#
# After running:
#   - Access Wiki.js at http://<container-ip>:3000
#   - Create admin account on first visit
#   - Configure git sync to Forgejo for automated backups
#
# Prerequisites:
#   - Container bootstrapped with systemd (entrypoint removed)
#   - SSH keys injected
#
# Source: https://docs.requarks.io/install

set -euo pipefail

# --- Configuration ---
WIKIJS_VERSION="2.5.304"
INSTALL_DIR="/opt/wikijs"
DB_NAME="wikijs"
DB_USER="wikijs"
DB_PASS="$(tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 32)"
WIKIJS_PORT=3000

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

# --- Step 1: Install Node.js 18 LTS ---
step 1 "Installing Node.js 18 LTS"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends curl ca-certificates gnupg >/dev/null 2>&1

if command -v node &>/dev/null; then
    info "Node.js already installed: $(node --version)"
else
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash -
    apt-get install -y nodejs >/dev/null 2>&1
    info "Node.js $(node --version) installed"
fi

# --- Step 2: Install PostgreSQL ---
step 2 "Installing PostgreSQL"
apt-get install -y --no-install-recommends postgresql >/dev/null 2>&1

# Start PostgreSQL
if command -v systemctl &>/dev/null && systemctl is-system-running &>/dev/null; then
    systemctl start postgresql
    systemctl enable postgresql
else
    service postgresql start
    update-rc.d postgresql enable
fi
info "PostgreSQL installed and running"

# --- Step 3: Create database ---
step 3 "Creating Wiki.js database"
if su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'\"" | grep -q 1; then
    info "Role '${DB_USER}' already exists"
else
    su - postgres -c "psql -c \"CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASS}';\""
    info "Created role '${DB_USER}'"
fi

if su - postgres -c "psql -tAc \"SELECT 1 FROM pg_catalog.pg_database WHERE datname='${DB_NAME}'\"" | grep -q 1; then
    info "Database '${DB_NAME}' already exists"
else
    su - postgres -c "psql -c \"CREATE DATABASE ${DB_NAME} WITH OWNER ${DB_USER};\""
    info "Created database '${DB_NAME}'"
fi

# --- Step 4: Download Wiki.js ---
step 4 "Downloading Wiki.js v${WIKIJS_VERSION}"
mkdir -p "$INSTALL_DIR"

if [ -f "$INSTALL_DIR/server/index.js" ]; then
    info "Wiki.js already downloaded — skipping"
else
    curl -fSL "https://github.com/requarks/wiki/releases/download/v${WIKIJS_VERSION}/wiki-js.tar.gz" \
        -o /tmp/wiki-js.tar.gz
    tar xzf /tmp/wiki-js.tar.gz -C "$INSTALL_DIR"
    rm -f /tmp/wiki-js.tar.gz
    info "Downloaded and extracted Wiki.js v${WIKIJS_VERSION}"
fi

# --- Step 5: Configure Wiki.js ---
step 5 "Configuring Wiki.js"
cat > "$INSTALL_DIR/config.yml" << EOF
port: ${WIKIJS_PORT}
bindIP: 0.0.0.0

db:
  type: postgres
  host: localhost
  port: 5432
  user: ${DB_USER}
  pass: ${DB_PASS}
  db: ${DB_NAME}
  ssl: false

logLevel: info
ha: false
dataPath: ./data
EOF

mkdir -p "$INSTALL_DIR/data"
info "Configuration written to $INSTALL_DIR/config.yml"

# --- Step 6: Create wikijs system user ---
step 6 "Creating wikijs system user"
useradd --system --shell /usr/sbin/nologin --home-dir "$INSTALL_DIR" wikijs 2>/dev/null || true
chown -R wikijs:wikijs "$INSTALL_DIR"
info "User 'wikijs' ready"

# --- Step 7: Create systemd service ---
step 7 "Creating systemd service"
cat > /etc/systemd/system/wikijs.service << 'UNIT'
[Unit]
Description=Wiki.js — Personal Knowledge Wiki
After=network.target postgresql.service

[Service]
Type=simple
User=wikijs
Group=wikijs
WorkingDirectory=/opt/wikijs
ExecStart=/usr/bin/node server
Restart=on-failure
RestartSec=5
Environment=NODE_ENV=production

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable wikijs
info "Systemd service created and enabled"

# --- Step 8: Start Wiki.js ---
step 8 "Starting Wiki.js"
systemctl start wikijs

# First start takes longer — Wiki.js initializes the database schema
info "Waiting for Wiki.js to initialize (first start takes ~15s)..."
for i in $(seq 1 20); do
    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:${WIKIJS_PORT}/ 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" != "000" ]; then
        break
    fi
    sleep 2
done

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
    info "Wiki.js is running! (HTTP ${HTTP_CODE})"
else
    warn "Wiki.js may still be initializing (HTTP ${HTTP_CODE})"
    warn "Check: journalctl -u wikijs -f"
fi

# --- Summary ---
CONTAINER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Wiki.js v${WIKIJS_VERSION} installed successfully!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Access:    http://${CONTAINER_IP}:${WIKIJS_PORT}"
echo "  Config:    ${INSTALL_DIR}/config.yml"
echo "  Data:      ${INSTALL_DIR}/data"
echo "  DB Name:   ${DB_NAME}"
echo "  DB User:   ${DB_USER}"
echo "  DB Pass:   ${DB_PASS}"
echo "  Service:   systemctl {start|stop|restart|status} wikijs"
echo ""
echo "  Create your admin account on first visit."
echo ""
echo -e "  ${YELLOW}SAVE THE DATABASE PASSWORD ABOVE — randomly generated.${NC}"
echo ""
echo "  Tip: Configure git storage in Admin > Storage to sync"
echo "       your wiki content to Forgejo for automated backups."
echo ""
