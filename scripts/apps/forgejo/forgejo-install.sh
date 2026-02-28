#!/bin/bash
# install-forgejo.sh — Install Forgejo on Debian Bookworm LXC container
#
# Usage: Run inside a fresh Debian 12 (Bookworm) LXC container via Proxmox console:
#   bash install-forgejo.sh
#
# What it does:
#   1. Installs system packages (git, postgresql, wget, ca-certificates)
#   2. Creates PostgreSQL database + role for Forgejo
#   3. Creates 'git' system user + required directories
#   4. Downloads Forgejo binary (v14.0.2)
#   5. Writes minimal app.ini config (auto-detects container IP)
#   6. Creates + enables init.d service (SysV — no systemd in LXC)
#   7. Starts Forgejo and verifies it's running
#
# After running, visit http://<container-ip>:3000/ to complete web setup.
#
# Sources:
#   - https://forgejo.org/docs/next/admin/installation/binary/
#   - https://forgejo.org/docs/latest/admin/installation/database-preparation/

set -euo pipefail

FORGEJO_VERSION="14.0.2"
FORGEJO_ARCH="linux-amd64"
FORGEJO_URL="https://codeberg.org/forgejo/forgejo/releases/download/v${FORGEJO_VERSION}/forgejo-${FORGEJO_VERSION}-${FORGEJO_ARCH}"
DB_NAME="forgejodb"
DB_USER="forgejo"
DB_PASS="forgejo"

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

if ! grep -q 'bookworm' /etc/os-release 2>/dev/null; then
    warn "Expected Debian Bookworm — detected: $(. /etc/os-release && echo "$PRETTY_NAME")"
    warn "Continuing anyway..."
fi

# --- Step 1: System packages ---
step 1 "Installing system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git git-lfs wget ca-certificates postgresql curl iproute2 procps >/dev/null 2>&1
info "Packages installed"

# --- Step 2: PostgreSQL setup ---
step 2 "Configuring PostgreSQL"

# Start PostgreSQL if not running
service postgresql start
update-rc.d postgresql enable

# Create role and database (idempotent)
if su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'\"" | grep -q 1; then
    info "PostgreSQL role '${DB_USER}' already exists"
else
    su - postgres -c "psql -c \"CREATE ROLE ${DB_USER} WITH LOGIN PASSWORD '${DB_PASS}';\""
    info "Created PostgreSQL role '${DB_USER}'"
fi

if su - postgres -c "psql -tAc \"SELECT 1 FROM pg_catalog.pg_database WHERE datname='${DB_NAME}'\"" | grep -q 1; then
    info "Database '${DB_NAME}' already exists"
else
    su - postgres -c "psql -c \"CREATE DATABASE ${DB_NAME} WITH OWNER ${DB_USER} TEMPLATE template0 ENCODING UTF8 LC_COLLATE 'C.UTF-8' LC_CTYPE 'C.UTF-8';\""
    info "Created database '${DB_NAME}'"
fi

# Configure pg_hba for scram-sha-256 auth (idempotent)
PG_HBA=$(find /etc/postgresql -name pg_hba.conf -print -quit)
if [ -z "$PG_HBA" ]; then
    error "Could not find pg_hba.conf"
    exit 1
fi

if ! grep -q "forgejo" "$PG_HBA"; then
    # Insert before the first 'local all all' line
    sed -i "/^local\s\+all\s\+all/i local ${DB_NAME} ${DB_USER} scram-sha-256" "$PG_HBA"
    service postgresql restart
    info "Updated pg_hba.conf and restarted PostgreSQL"
else
    info "pg_hba.conf already configured for forgejo"
fi

# --- Step 3: Git user + directories ---
step 3 "Creating git user and directories"

if id git &>/dev/null; then
    info "User 'git' already exists"
else
    adduser --system --shell /bin/bash --gecos "Git Version Control" \
        --group --disabled-password --home /home/git git
    info "Created system user 'git'"
fi

install -d -m 750 -o git -g git /var/lib/forgejo
install -d -m 750 -o git -g git /var/lib/forgejo/log
install -d -m 770 -o root -g git /etc/forgejo
info "Directories ready"

# --- Step 4: Download Forgejo binary ---
step 4 "Downloading Forgejo v${FORGEJO_VERSION}"

mkdir -p /opt/forgejo
if [ -f /opt/forgejo/forgejo ] && /opt/forgejo/forgejo --version 2>/dev/null | grep -q "${FORGEJO_VERSION}"; then
    info "Forgejo v${FORGEJO_VERSION} already installed"
else
    wget -q --show-progress -O /opt/forgejo/forgejo "$FORGEJO_URL"
    chmod 755 /opt/forgejo/forgejo
    info "Downloaded Forgejo v${FORGEJO_VERSION}"
fi

ln -sf /opt/forgejo/forgejo /usr/local/bin/forgejo

# --- Step 5: Write app.ini ---
step 5 "Writing Forgejo config"

# Auto-detect container IP (first non-loopback IPv4)
CONTAINER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')
if [ -z "$CONTAINER_IP" ]; then
    # Fallback: parse ip addr (hostname -I may not exist in minimal LXC)
    CONTAINER_IP=$(ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -1)
fi
if [ -z "$CONTAINER_IP" ]; then
    warn "Could not detect container IP — using 0.0.0.0"
    CONTAINER_IP="0.0.0.0"
fi
info "Detected container IP: ${CONTAINER_IP}"

# Only write config if it doesn't exist (preserve manual edits)
if [ -f /etc/forgejo/app.ini ]; then
    warn "app.ini already exists — skipping (delete it to regenerate)"
else
    cat > /etc/forgejo/app.ini << EOF
APP_NAME = Forgejo

[database]
DB_TYPE  = postgres
HOST     = 127.0.0.1:5432
NAME     = ${DB_NAME}
USER     = ${DB_USER}
PASSWD   = ${DB_PASS}

[server]
HTTP_PORT        = 3000
DOMAIN           = ${CONTAINER_IP}
ROOT_URL         = http://${CONTAINER_IP}:3000/
SSH_PORT         = 22
SSH_DOMAIN       = ${CONTAINER_IP}
DISABLE_SSH      = false
START_SSH_SERVER = false

[repository]
ROOT = /home/git/forgejo-repositories

[log]
ROOT_PATH = /var/lib/forgejo/log
MODE      = file
LEVEL     = Info
EOF
    chown root:git /etc/forgejo/app.ini
    chmod 660 /etc/forgejo/app.ini
    info "Wrote /etc/forgejo/app.ini"
fi

# --- Step 6: Init.d service (SysV — LXC containers don't have systemd) ---
step 6 "Creating init.d service"

cat > /etc/init.d/forgejo << 'INITEOF'
#!/bin/sh
### BEGIN INIT INFO
# Provides:          forgejo
# Required-Start:    $local_fs $network postgresql
# Required-Stop:     $local_fs $network
# Default-Start:     2 3 4 5
# Default-Stop:      0 1 6
# Short-Description: Forgejo git hosting
# Description:       Forgejo - self-hosted lightweight git service
### END INIT INFO

DAEMON=/usr/local/bin/forgejo
DAEMON_ARGS="web --config /etc/forgejo/app.ini"
NAME=forgejo
PIDFILE=/var/run/forgejo.pid
LOGFILE=/var/lib/forgejo/log/forgejo-init.log
USER=git
GROUP=git
WORKDIR=/var/lib/forgejo

export USER HOME=/home/git FORGEJO_WORK_DIR=/var/lib/forgejo

do_start() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "$NAME is already running"
        return 0
    fi
    echo "Starting $NAME..."
    start-stop-daemon --start --quiet --background \
        --make-pidfile --pidfile "$PIDFILE" \
        --chuid "$USER:$GROUP" --chdir "$WORKDIR" \
        --exec "$DAEMON" -- $DAEMON_ARGS
}

do_stop() {
    if [ ! -f "$PIDFILE" ] || ! kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "$NAME is not running"
        return 0
    fi
    echo "Stopping $NAME..."
    start-stop-daemon --stop --quiet --pidfile "$PIDFILE" --retry=TERM/10/KILL/5
    rm -f "$PIDFILE"
}

do_status() {
    if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "$NAME is running (PID $(cat "$PIDFILE"))"
        return 0
    else
        echo "$NAME is not running"
        return 1
    fi
}

case "$1" in
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_stop; do_start ;;
    status)  do_status ;;
    *)       echo "Usage: $0 {start|stop|restart|status}"; exit 1 ;;
esac
INITEOF

chmod 755 /etc/init.d/forgejo
update-rc.d forgejo defaults
info "Init.d service created and enabled"

# --- Step 7: Start and verify ---
step 7 "Starting Forgejo"

service forgejo start
sleep 3

if service forgejo status >/dev/null 2>&1; then
    info "Forgejo is running"
else
    error "Forgejo failed to start. Check: /var/lib/forgejo/log/forgejo-init.log"
    exit 1
fi

# Wait for HTTP to come up (up to 15s)
for i in $(seq 1 15); do
    HTTP_CODE=$(curl -s -o /dev/null -w '%{http_code}' http://localhost:3000/ 2>/dev/null || echo "000")
    if [ "$HTTP_CODE" != "000" ]; then
        break
    fi
    sleep 1
done

if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "302" ]; then
    info "HTTP responding (status ${HTTP_CODE})"
else
    warn "HTTP not responding yet (status ${HTTP_CODE}) — may still be starting"
fi

# --- Summary ---
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  Forgejo v${FORGEJO_VERSION} installed successfully${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "  Web UI:     http://${CONTAINER_IP}:3000/"
echo "  Config:     /etc/forgejo/app.ini"
echo "  Data:       /var/lib/forgejo/"
echo "  Repos:      /home/git/forgejo-repositories/"
echo "  Logs:       /var/lib/forgejo/log/"
echo "  Service:    service forgejo status"
echo ""
echo "  Visit the web UI to create your admin account."
echo ""
