#!/bin/bash
# install-wiki.sh — Complete Wiki.js + Kiwix + Forgejo git sync on Debian Bookworm LXC
#
# Usage: Run inside a bootstrapped Debian 12 LXC container:
#   bash install-wiki.sh
#
# What it does:
#   1. Installs Node.js 18 LTS, PostgreSQL, git, kiwix-tools
#   2. Creates PostgreSQL database for Wiki.js
#   3. Downloads and configures Wiki.js v2.5.304
#   4. Installs Kiwix server for offline Wikipedia (port 8080)
#   5. If ~/.git-credentials exists: sets up Forgejo git sync
#      - Clones servermonkey repo from Forgejo
#      - Creates wiki-content repo on Forgejo for Wiki.js storage
#      - Creates systemd timer for auto-pull every 15 min
#   6. Creates systemd services for all components
#   7. Starts everything
#
# Prerequisites:
#   - Container bootstrapped with systemd (entrypoint removed, SSH working)
#   - SCP ~/.git-credentials to container before running (for Forgejo sync)
#
# Deploy from your Proxmox admin host:
#   scp ~/.git-credentials root@<wiki-ip>:/root/.git-credentials
#   ssh root@<wiki-ip> 'bash -s' < scripts/apps/wiki/install-wiki.sh
#
# After running (manual steps):
#   1. Visit http://<ip>:3000 — create admin account
#   2. Admin > Storage > Git — point at wiki-content repo on Forgejo
#   3. Download Wikipedia ZIM file (see instructions at end)
#
# Sources:
#   - https://docs.requarks.io/install
#   - https://kiwix.org

set -euo pipefail

# ═══════════════════════════════════════════
# Configuration
# ═══════════════════════════════════════════
WIKIJS_VERSION="2.5.304"
WIKIJS_DIR="/opt/wikijs"
WIKIJS_PORT=3000

KIWIX_DIR="/opt/kiwix"
KIWIX_PORT=8080

DB_NAME="wikijs"
DB_USER="wikijs"
DB_PASS="$(tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 32)"

FORGEJO_HOST="forgejo.example.com"
FORGEJO_PORT="63179"
FORGEJO_USER="robot"
FORGEJO_URL="http://${FORGEJO_HOST}:${FORGEJO_PORT}"
SERVERMONKEY_REPO="${FORGEJO_URL}/${FORGEJO_USER}/servermonkey.git"
WIKI_CONTENT_REPO="wiki-content"

GIT_SYNC_DIR="/opt/servermonkey"
GIT_SYNC_INTERVAL="15min"

# ═══════════════════════════════════════════
# Output helpers
# ═══════════════════════════════════════════
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

info()    { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
step()    { echo -e "\n${GREEN}━━━ Step $1: $2 ━━━${NC}"; }
section() { echo -e "\n${BLUE}═══ $1 ═══${NC}"; }

# ═══════════════════════════════════════════
# Preflight
# ═══════════════════════════════════════════
if [ "$(id -u)" -ne 0 ]; then
    error "Must run as root"
    exit 1
fi

if ! grep -qi 'debian' /etc/os-release 2>/dev/null; then
    warn "Expected Debian — detected: $(. /etc/os-release && echo "$PRETTY_NAME")"
fi

HAS_FORGEJO_CREDS=false
if [ -f /root/.git-credentials ] && grep -q "forgejo" /root/.git-credentials; then
    HAS_FORGEJO_CREDS=true
    info "Forgejo credentials found — git sync will be configured"
else
    warn "No Forgejo credentials found at /root/.git-credentials"
    warn "Git sync will be skipped. To enable later:"
    warn "  scp ~/.git-credentials root@\$(hostname -I | awk '{print \$1}'):/root/.git-credentials"
fi

# ═══════════════════════════════════════════
# PART 1: WIKI.JS
# ═══════════════════════════════════════════
section "WIKI.JS INSTALLATION"

# --- Step 1: System packages ---
step 1 "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends \
    curl ca-certificates gnupg git wget lsb-release iproute2 cron >/dev/null 2>&1
info "Base packages installed"

# --- Step 2: Node.js 18 LTS ---
step 2 "Installing Node.js 18 LTS"
if command -v node &>/dev/null; then
    info "Node.js already installed: $(node --version)"
else
    curl -fsSL https://deb.nodesource.com/setup_18.x | bash - >/dev/null 2>&1
    apt-get install -y nodejs >/dev/null 2>&1
    info "Node.js $(node --version) installed"
fi

# --- Step 3: PostgreSQL ---
step 3 "Installing PostgreSQL"
apt-get install -y --no-install-recommends postgresql >/dev/null 2>&1
systemctl start postgresql
systemctl enable postgresql
info "PostgreSQL installed and running"

# --- Step 4: Create database ---
step 4 "Creating Wiki.js database"
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

# --- Step 5: Download Wiki.js ---
step 5 "Downloading Wiki.js v${WIKIJS_VERSION}"
mkdir -p "$WIKIJS_DIR"

if [ -f "$WIKIJS_DIR/server/index.js" ]; then
    info "Wiki.js already downloaded — skipping"
else
    curl -fSL "https://github.com/requarks/wiki/releases/download/v${WIKIJS_VERSION}/wiki-js.tar.gz" \
        -o /tmp/wiki-js.tar.gz
    tar xzf /tmp/wiki-js.tar.gz -C "$WIKIJS_DIR"
    rm -f /tmp/wiki-js.tar.gz
    info "Downloaded and extracted Wiki.js v${WIKIJS_VERSION}"
fi

# --- Step 6: Configure Wiki.js ---
step 6 "Configuring Wiki.js"
cat > "$WIKIJS_DIR/config.yml" << EOF
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

mkdir -p "$WIKIJS_DIR/data"
info "Configuration written"

# --- Step 7: Create wikijs user and service ---
step 7 "Creating wikijs user and systemd service"
useradd --system --shell /usr/sbin/nologin --home-dir "$WIKIJS_DIR" wikijs 2>/dev/null || true
chown -R wikijs:wikijs "$WIKIJS_DIR"

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
info "Service created and enabled"

# --- Step 8: Start Wiki.js ---
step 8 "Starting Wiki.js"
systemctl start wikijs

info "Waiting for Wiki.js to initialize (first start takes ~15-30s)..."
for i in $(seq 1 30); do
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

# ═══════════════════════════════════════════
# PART 2: KIWIX
# ═══════════════════════════════════════════
section "KIWIX INSTALLATION"

# --- Step 9: Install kiwix-tools ---
step 9 "Installing kiwix-tools"
apt-get install -y --no-install-recommends kiwix-tools >/dev/null 2>&1

if command -v kiwix-serve &>/dev/null; then
    info "kiwix-serve installed: $(kiwix-serve --version 2>&1 | head -1)"
else
    error "kiwix-serve not found after install"
    # Non-fatal — continue with wiki.js
fi

# --- Step 10: Create kiwix directories and service ---
step 10 "Configuring Kiwix server"
mkdir -p "$KIWIX_DIR/library"
useradd --system --shell /usr/sbin/nologin --home-dir "$KIWIX_DIR" kiwix 2>/dev/null || true
chown -R kiwix:kiwix "$KIWIX_DIR"

# Launcher script (kiwix-serve needs explicit file paths, no glob in ExecStart)
cat > /usr/local/bin/kiwix-start.sh << 'LAUNCHER'
#!/bin/bash
ZIM_DIR="/opt/kiwix/library"
ZIM_FILES=$(find "$ZIM_DIR" -name "*.zim" -type f 2>/dev/null | tr '\n' ' ')

if [ -z "$ZIM_FILES" ]; then
    echo "No ZIM files found in $ZIM_DIR — waiting for downloads..."
    sleep infinity
fi

exec /usr/bin/kiwix-serve --port 8080 --address 0.0.0.0 $ZIM_FILES
LAUNCHER
chmod 755 /usr/local/bin/kiwix-start.sh

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
info "Kiwix service created (will serve ZIM files when downloaded)"

# ═══════════════════════════════════════════
# PART 3: FORGEJO GIT SYNC
# ═══════════════════════════════════════════
if [ "$HAS_FORGEJO_CREDS" = true ]; then
    section "FORGEJO GIT SYNC"

    # Extract password from git-credentials for API calls
    FORGEJO_PASS=$(grep "forgejo" /root/.git-credentials | sed 's|.*://[^:]*:\([^@]*\)@.*|\1|')

    # --- Step 11: Configure git ---
    step 11 "Configuring git credential helper"
    git config --global credential.helper store
    git config --global user.name "robot"
    git config --global user.email "robot@wiki"
    # Credentials file already in place from SCP
    info "Git credentials configured"

    # --- Step 12: Clone servermonkey repo ---
    step 12 "Cloning servermonkey repo from Forgejo"
    if [ -d "$GIT_SYNC_DIR/.git" ]; then
        info "Repo already cloned at $GIT_SYNC_DIR"
        cd "$GIT_SYNC_DIR" && git pull --ff-only && cd /
    else
        git clone "$SERVERMONKEY_REPO" "$GIT_SYNC_DIR"
        info "Cloned to $GIT_SYNC_DIR"
    fi

    # --- Step 13: Create wiki-content repo on Forgejo ---
    step 13 "Creating wiki-content repo on Forgejo"

    # Check if repo already exists
    REPO_CHECK=$(curl -s -o /dev/null -w '%{http_code}' \
        -u "${FORGEJO_USER}:${FORGEJO_PASS}" \
        "${FORGEJO_URL}/api/v1/repos/${FORGEJO_USER}/${WIKI_CONTENT_REPO}")

    if [ "$REPO_CHECK" = "200" ]; then
        info "Repo '${WIKI_CONTENT_REPO}' already exists on Forgejo"
    else
        CREATE_RESULT=$(curl -s -w '\n%{http_code}' \
            -X POST "${FORGEJO_URL}/api/v1/user/repos" \
            -u "${FORGEJO_USER}:${FORGEJO_PASS}" \
            -H "Content-Type: application/json" \
            -d "{
                \"name\": \"${WIKI_CONTENT_REPO}\",
                \"description\": \"Wiki.js content — auto-synced from wiki container\",
                \"private\": true,
                \"auto_init\": true,
                \"default_branch\": \"main\"
            }")

        CREATE_CODE=$(echo "$CREATE_RESULT" | tail -1)
        if [ "$CREATE_CODE" = "201" ] || [ "$CREATE_CODE" = "409" ]; then
            info "Repo '${WIKI_CONTENT_REPO}' ready on Forgejo"
        else
            warn "Could not create '${WIKI_CONTENT_REPO}' repo (HTTP ${CREATE_CODE})"
            warn "You may need to create it manually in the Forgejo UI"
        fi
    fi

    # --- Step 14: Set up git-sync systemd timer ---
    step 14 "Creating git-sync systemd timer"

    cat > /etc/systemd/system/git-sync.service << 'SYNCUNIT'
[Unit]
Description=Git sync — pull servermonkey from Forgejo

[Service]
Type=oneshot
WorkingDirectory=/opt/servermonkey
ExecStart=/usr/bin/git pull --ff-only
User=root
StandardOutput=journal
StandardError=journal
SYNCUNIT

    cat > /etc/systemd/system/git-sync.timer << TIMERUNIT
[Unit]
Description=Git sync every ${GIT_SYNC_INTERVAL}

[Timer]
OnBootSec=60
OnUnitActiveSec=${GIT_SYNC_INTERVAL}
Persistent=true

[Install]
WantedBy=timers.target
TIMERUNIT

    systemctl daemon-reload
    systemctl enable --now git-sync.timer
    info "Git sync timer active (pulls every ${GIT_SYNC_INTERVAL})"
    info "Manual sync: systemctl start git-sync"

else
    section "GIT SYNC SKIPPED"
    warn "No Forgejo credentials — git sync not configured"
    warn "To enable later, SCP credentials and re-run this section"
fi

# ═══════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════
CONTAINER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  Wiki container — Installation Complete${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
echo -e "  ${BLUE}── Wiki.js ──${NC}"
echo "  URL:       http://${CONTAINER_IP}:${WIKIJS_PORT}"
echo "  Config:    ${WIKIJS_DIR}/config.yml"
echo "  DB Name:   ${DB_NAME}"
echo "  DB User:   ${DB_USER}"
echo "  DB Pass:   ${DB_PASS}"
echo "  Service:   systemctl {start|stop|restart|status} wikijs"
echo ""
echo -e "  ${BLUE}── Kiwix ──${NC}"
echo "  URL:       http://${CONTAINER_IP}:${KIWIX_PORT} (after ZIM download)"
echo "  Library:   ${KIWIX_DIR}/library/"
echo "  Service:   systemctl {start|stop|restart|status} kiwix"
echo ""

if [ "$HAS_FORGEJO_CREDS" = true ]; then
echo -e "  ${BLUE}── Git Sync ──${NC}"
echo "  Repo:      ${GIT_SYNC_DIR} (auto-pulls every ${GIT_SYNC_INTERVAL})"
echo "  Manual:    systemctl start git-sync"
echo "  Timer:     systemctl list-timers git-sync.timer"
echo "  Wiki repo: ${FORGEJO_URL}/${FORGEJO_USER}/${WIKI_CONTENT_REPO}"
echo ""
fi

echo -e "  ${YELLOW}═══ SAVE THIS ═══${NC}"
echo -e "  ${YELLOW}DB Password: ${DB_PASS}${NC}"
echo ""
echo -e "  ${BLUE}── Manual Steps ──${NC}"
echo ""
echo "  1. WIKI.JS SETUP"
echo "     Visit http://${CONTAINER_IP}:${WIKIJS_PORT}"
echo "     → Create your admin account (email + password)"
echo "     → You're in — start creating wiki pages"
echo ""
echo "  2. WIKI.JS GIT STORAGE (optional, recommended)"
echo "     → Admin Panel > Storage > Git"
echo "     → Authentication Type: basic"
echo "     → Repo URL:  ${FORGEJO_URL}/${FORGEJO_USER}/${WIKI_CONTENT_REPO}.git"
echo "     → Branch:    main"
echo "     → Username:  ${FORGEJO_USER}"
echo "     → Password:  (your Forgejo password)"
echo "     → Sync Direction: Bi-directional"
echo "     → Click the green checkmark to enable"
echo "     → Every wiki edit will be committed to Forgejo"
echo ""
echo "  3. DOWNLOAD WIKIPEDIA"
echo "     SSH in and run:"
echo "     cd ${KIWIX_DIR}/library"
echo ""
echo "     # Text only (~7 GB):"
echo "     wget https://download.kiwix.org/zim/wikipedia_en_all_nopic.zim"
echo ""
echo "     # With images (~100 GB):"
echo "     wget https://download.kiwix.org/zim/wikipedia_en_all_maxi.zim"
echo ""
echo "     # Then:"
echo "     chown -R kiwix:kiwix ${KIWIX_DIR}/library"
echo "     systemctl restart kiwix"
echo ""
echo "     Browse ZIM catalog: https://download.kiwix.org/zim/"
echo ""
echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
echo ""
