#!/bin/bash
# install-vecdb.sh — Install PostgreSQL 16 + pgvector on Debian Bookworm LXC
#
# Usage: Run inside a fresh Debian 12 (Bookworm) LXC container:
#   bash install-vecdb.sh
#
# What it does:
#   1. Adds PostgreSQL PGDG repository
#   2. Installs PostgreSQL 16 + pgvector extension
#   3. Creates 'aimemory' database with vector extension enabled
#   4. Creates starter schema (memories table with HNSW index)
#   5. Configures network access for the configured VLAN subnet (set VLAN_SUBNET; default 10.0.0.0/24)
#   6. Enables and starts PostgreSQL
#
# After running:
#   - Connect: psql -h <container-ip> -U ai -d aimemory
#   - Python:  pip install psycopg2-binary pgvector
#
# Prerequisites:
#   - Container bootstrapped with systemd (entrypoint removed)
#   - SSH keys injected
#
# Source: https://github.com/pgvector/pgvector

set -euo pipefail

# --- Configuration ---
DB_NAME="aimemory"
DB_USER="ai"
DB_PASS="$(tr -dc 'a-zA-Z0-9' < /dev/urandom | head -c 32)"
VLAN_SUBNET="${VLAN_SUBNET:-10.0.0.0/24}"
PG_VERSION="16"

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

# --- Step 1: Add PostgreSQL PGDG repository ---
step 1 "Adding PostgreSQL PGDG repository"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y --no-install-recommends curl ca-certificates gnupg lsb-release >/dev/null 2>&1

# Add PGDG signing key and repo
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
    | gpg --dearmor -o /etc/apt/trusted.gpg.d/postgresql.gpg
echo "deb https://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
    > /etc/apt/sources.list.d/pgdg.list
apt-get update -qq
info "PGDG repository added"

# --- Step 2: Install PostgreSQL 16 + pgvector ---
step 2 "Installing PostgreSQL ${PG_VERSION} + pgvector"
apt-get install -y --no-install-recommends \
    postgresql-${PG_VERSION} \
    postgresql-${PG_VERSION}-pgvector >/dev/null 2>&1

# Start PostgreSQL
if command -v systemctl &>/dev/null && systemctl is-system-running &>/dev/null; then
    systemctl start postgresql
    systemctl enable postgresql
else
    service postgresql start
    update-rc.d postgresql enable
fi
info "PostgreSQL ${PG_VERSION} + pgvector installed"

# --- Step 3: Configure network access ---
step 3 "Configuring network access"

# Find config files
PG_CONF=$(find /etc/postgresql -name postgresql.conf -path "*/${PG_VERSION}/*" -print -quit)
PG_HBA=$(find /etc/postgresql -name pg_hba.conf -path "*/${PG_VERSION}/*" -print -quit)

if [ -z "$PG_CONF" ] || [ -z "$PG_HBA" ]; then
    error "Could not find PostgreSQL config files"
    exit 1
fi

# Listen on all interfaces (not just localhost)
if grep -q "^listen_addresses" "$PG_CONF"; then
    sed -i "s/^listen_addresses.*/listen_addresses = '*'/" "$PG_CONF"
else
    echo "listen_addresses = '*'" >> "$PG_CONF"
fi
info "Set listen_addresses = '*'"

# Allow connections from the configured VLAN subnet
if ! grep -q "${DB_USER}" "$PG_HBA"; then
    echo "" >> "$PG_HBA"
    echo "# AI memory — allow connections from VLAN subnet" >> "$PG_HBA"
    echo "host    ${DB_NAME}    ${DB_USER}    ${VLAN_SUBNET}    scram-sha-256" >> "$PG_HBA"
    info "Added pg_hba rule for ${VLAN_SUBNET}"
else
    info "pg_hba.conf already configured for ${DB_USER}"
fi

# Restart to apply network config
if command -v systemctl &>/dev/null && systemctl is-system-running &>/dev/null; then
    systemctl restart postgresql
else
    service postgresql restart
fi
sleep 2
info "PostgreSQL restarted with network config"

# --- Step 4: Create database and user ---
step 4 "Creating AI memory database"

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

# --- Step 5: Enable pgvector extension and create schema ---
step 5 "Enabling pgvector and creating AI memory schema"

su - postgres -c "psql -d ${DB_NAME}" << 'SCHEMA'
-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- Memories table: core storage for AI knowledge with vector embeddings
CREATE TABLE IF NOT EXISTS memories (
    id          BIGSERIAL PRIMARY KEY,
    content     TEXT NOT NULL,
    embedding   vector(1536),
    metadata    JSONB DEFAULT '{}',
    source      TEXT,
    category    TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- HNSW index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_memories_embedding
    ON memories USING hnsw (embedding vector_cosine_ops);

-- Full-text search on content
CREATE INDEX IF NOT EXISTS idx_memories_content_fts
    ON memories USING gin (to_tsvector('english', content));

-- Filter by category and source
CREATE INDEX IF NOT EXISTS idx_memories_category ON memories (category);
CREATE INDEX IF NOT EXISTS idx_memories_source ON memories (source);

-- JSONB metadata queries
CREATE INDEX IF NOT EXISTS idx_memories_metadata ON memories USING gin (metadata);

-- Grant permissions to the ai user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO ai;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO ai;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO ai;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON SEQUENCES TO ai;
SCHEMA

info "pgvector enabled, 'memories' table and indexes created"

# --- Step 6: Verify installation ---
step 6 "Verifying installation"

# Check pgvector extension
PGVECTOR_VERSION=$(su - postgres -c "psql -tAc \"SELECT extversion FROM pg_extension WHERE extname='vector';\" -d ${DB_NAME}")
if [ -n "$PGVECTOR_VERSION" ]; then
    info "pgvector v${PGVECTOR_VERSION} active"
else
    error "pgvector extension not found"
    exit 1
fi

# Test vector operations
TEST_RESULT=$(su - postgres -c "psql -tAc \"SELECT '[1,2,3]'::vector <=> '[4,5,6]'::vector;\" -d ${DB_NAME}")
if [ -n "$TEST_RESULT" ]; then
    info "Vector operations working (cosine distance test passed)"
else
    error "Vector operations failed"
    exit 1
fi

# Check network listener
PG_PORT=$(su - postgres -c "psql -tAc \"SHOW port;\"" | tr -d ' ')
if ss -tlnp | grep -q ":${PG_PORT}.*0.0.0.0"; then
    info "PostgreSQL listening on 0.0.0.0:${PG_PORT}"
else
    warn "PostgreSQL may only be listening on localhost — check listen_addresses"
fi

# --- Summary ---
CONTAINER_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  PostgreSQL ${PG_VERSION} + pgvector installed!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Host:      ${CONTAINER_IP}"
echo "  Port:      ${PG_PORT}"
echo "  Database:  ${DB_NAME}"
echo "  User:      ${DB_USER}"
echo "  Password:  ${DB_PASS}"
echo "  pgvector:  v${PGVECTOR_VERSION}"
echo ""
echo "  Connect:   psql -h ${CONTAINER_IP} -U ${DB_USER} -d ${DB_NAME}"
echo "  Service:   systemctl {start|stop|restart|status} postgresql"
echo ""
echo -e "  ${YELLOW}SAVE THE PASSWORD ABOVE — randomly generated.${NC}"
echo ""
echo "  ━━━ Schema ━━━"
echo ""
echo "  Table 'memories' created with columns:"
echo "    id, content, embedding (vector 1536d), metadata (JSONB),"
echo "    source, category, created_at, updated_at"
echo ""
echo "  Indexes: HNSW (cosine similarity), GIN (full-text + JSONB)"
echo ""
echo "  ━━━ Quick Start (Python) ━━━"
echo ""
echo "  pip install psycopg2-binary pgvector"
echo ""
echo "  import psycopg2"
echo "  from pgvector.psycopg2 import register_vector"
echo ""
echo "  conn = psycopg2.connect("
echo "      host='${CONTAINER_IP}', dbname='${DB_NAME}',"
echo "      user='${DB_USER}', password='<your-password>')"
echo "  register_vector(conn)"
echo ""
echo "  # Insert a memory"
echo "  cur = conn.cursor()"
echo "  cur.execute("
echo "      'INSERT INTO memories (content, embedding, category) VALUES (%s, %s, %s)',"
echo "      ('AI research note', [0.1]*1536, 'research'))"
echo ""
echo "  # Find similar memories"
echo "  cur.execute("
echo "      'SELECT content, 1-(embedding <=> %s) AS similarity FROM memories ORDER BY embedding <=> %s LIMIT 5',"
echo "      ([0.1]*1536, [0.1]*1536))"
echo ""
echo "  ━━━ Embedding Dimensions ━━━"
echo ""
echo "  The default 'memories' table uses 1536 dimensions (OpenAI ada-002)."
echo "  To change for other models:"
echo "    ALTER TABLE memories ALTER COLUMN embedding TYPE vector(768);  -- BGE/E5"
echo "    ALTER TABLE memories ALTER COLUMN embedding TYPE vector(3072); -- OpenAI large"
echo ""
