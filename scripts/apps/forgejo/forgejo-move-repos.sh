#!/bin/bash
# move-forgejo-repos.sh — Move Forgejo repository storage to a new location
#
# Usage: bash move-forgejo-repos.sh /new/path/to/repositories
#
# What it does:
#   1. Stops Forgejo service
#   2. Copies repo data to new location (preserving permissions)
#   3. Updates app.ini ROOT path
#   4. Restarts Forgejo and verifies
#   5. Prints instructions to remove old data after verification

set -euo pipefail

CONFIG="/etc/forgejo/app.ini"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

if [ "$(id -u)" -ne 0 ]; then
    error "Must run as root"
    exit 1
fi

if [ $# -ne 1 ]; then
    echo "Usage: $0 /new/path/to/repositories"
    exit 1
fi

NEW_ROOT="$1"

# --- Find current ROOT ---
if [ ! -f "$CONFIG" ]; then
    error "Config not found: $CONFIG"
    exit 1
fi

OLD_ROOT=$(grep -E '^\s*ROOT\s*=' "$CONFIG" | grep -v ROOT_PATH | head -1 | sed 's/.*=\s*//' | xargs)
if [ -z "$OLD_ROOT" ]; then
    error "Could not find repository ROOT in $CONFIG"
    exit 1
fi

info "Current repo location: $OLD_ROOT"
info "New repo location:     $NEW_ROOT"

if [ "$OLD_ROOT" = "$NEW_ROOT" ]; then
    error "Source and destination are the same"
    exit 1
fi

# --- Check source exists ---
if [ ! -d "$OLD_ROOT" ]; then
    warn "Source directory doesn't exist yet: $OLD_ROOT"
    warn "Nothing to move — just updating config"
    mkdir -p "$NEW_ROOT"
    chown git:git "$NEW_ROOT"
    chmod 750 "$NEW_ROOT"
    sed -i "s|^\(\s*ROOT\s*=\s*\).*|\1$NEW_ROOT|" "$CONFIG"
    # Only replace the first ROOT, not ROOT_PATH
    info "Updated $CONFIG"
    info "Done — no data to move"
    exit 0
fi

# --- Preflight: check disk space ---
USED=$(du -sb "$OLD_ROOT" 2>/dev/null | awk '{print $1}')
AVAIL=$(df --output=avail -B1 "$(dirname "$NEW_ROOT")" 2>/dev/null | tail -1 | xargs)
if [ -n "$USED" ] && [ -n "$AVAIL" ] && [ "$USED" -gt "$AVAIL" ]; then
    error "Not enough space. Need $(numfmt --to=iec "$USED"), have $(numfmt --to=iec "$AVAIL")"
    exit 1
fi
info "Data size: $(du -sh "$OLD_ROOT" | awk '{print $1}')"

# --- Stop Forgejo ---
info "Stopping Forgejo..."
service forgejo stop 2>/dev/null || true
sleep 2

if pgrep -x forgejo >/dev/null 2>&1; then
    error "Forgejo still running after stop"
    exit 1
fi
info "Forgejo stopped"

# --- Copy data (preserve permissions, links, timestamps) ---
info "Copying repositories to $NEW_ROOT..."
mkdir -p "$NEW_ROOT"
rsync -a --info=progress2 "$OLD_ROOT/" "$NEW_ROOT/"
chown -R git:git "$NEW_ROOT"
info "Copy complete"

# --- Update config ---
# Match ROOT = ... but not ROOT_PATH = ...
sed -i "/^\s*ROOT\s*=/{/ROOT_PATH/!s|=.*|= $NEW_ROOT|}" "$CONFIG"
info "Updated $CONFIG"

# --- Verify config ---
VERIFY_ROOT=$(grep -E '^\s*ROOT\s*=' "$CONFIG" | grep -v ROOT_PATH | head -1 | sed 's/.*=\s*//' | xargs)
if [ "$VERIFY_ROOT" != "$NEW_ROOT" ]; then
    error "Config verification failed. Expected: $NEW_ROOT, Got: $VERIFY_ROOT"
    error "Fix $CONFIG manually and restart Forgejo"
    exit 1
fi

# --- Restart ---
info "Starting Forgejo..."
service forgejo start
sleep 3

if service forgejo status >/dev/null 2>&1; then
    info "Forgejo is running"
else
    error "Forgejo failed to start — reverting config"
    sed -i "/^\s*ROOT\s*=/{/ROOT_PATH/!s|=.*|= $OLD_ROOT|}" "$CONFIG"
    service forgejo start
    error "Reverted to $OLD_ROOT. Check logs: /var/lib/forgejo/log/"
    exit 1
fi

# --- Summary ---
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  Repository storage moved successfully${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo "  Old location: $OLD_ROOT"
echo "  New location: $NEW_ROOT"
echo ""
echo "  Verify your repos work, then remove the old data:"
echo "    rm -rf $OLD_ROOT"
echo ""
