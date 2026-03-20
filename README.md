# ServerMonkey

Secure [MCP](https://modelcontextprotocol.io/) server for managing Proxmox VE infrastructure through Claude Code (or any MCP client). Credentials stay in your system keyring via libsecret — never on disk, never in environment variables.

## For MCP Clients

Start with `list_nodes` to discover the cluster, then explore from there.

**Tool categories:**

| Category | Tools | What they do |
|----------|-------|--------------|
| **Discover** | `list_nodes`, `node_status`, `cluster_resources` | Find nodes and check health |
| **Inventory** | `list_vms`, `list_containers`, `vm_status`, `ct_status`, `vm_config`, `ct_config` | See what's running and how it's configured |
| **Storage** | `list_storage`, `storage_content`, `list_available_templates` | Browse storage pools and templates |
| **Create** | `create_vm`, `create_container`, `clone_vm`, `clone_container` | Provision new guests |
| **Scale** | `resize_disk`, `update_cpu_memory` | Grow resources (never shrink) |
| **Lifecycle** | `start_guest`, `restart_guest`, `download_template` | Start, restart, fetch templates |
| **Execute** | `run_script` (pre-approved), `guest_exec` (requires approval) | Run commands inside guests |
| **Observe** | `list_tasks`, `task_status`, `list_snapshots` | Check task history and snapshots |
| **Admin** | `reconnect` | Reset the Proxmox API connection |

**Safety guarantees — the server will never:**
- Delete anything (VMs, containers, snapshots, backups, disk images)
- Stop a VM or container (only restart, and protected VMs can't even restart)
- Shrink a disk or reduce CPU/memory
- Download from non-HTTPS URLs or private/loopback IPs

**Script discovery:** If `run_script` returns "not found", the error message lists all available scripts — both flat scripts in `scripts/` and app module scripts in `scripts/apps/*/`.

## Features

- **27 MCP tools** for Proxmox management (15 read-only, 10 mutating, 2 guest execution)
- **libsecret credential management** — API tokens retrieved from GNOME Keyring / KDE Wallet at runtime
- **CA certificate pinning** — interactive setup with SHA-256 fingerprint verification
- **Guardrails** — input validation, resource caps, storage allowlists, protected VM enforcement
- **Audit logging** — every tool call logged to `~/.local/share/servermonkey/audit.jsonl` with file locking, rotation, and sensitive field redaction
- **Tiered guest execution** — pre-approved scripts run freely; arbitrary commands require human approval via Claude Code's permission system
- **Modular app scripts** — drop a directory into `scripts/apps/` to add new application management scripts with zero code changes
- **No destructive operations by design** — no delete, no stop, no shrink (enforced at client, server, and API layers)

## Tools

### Read-Only

| Tool | Description |
|------|-------------|
| `list_nodes` | List all cluster nodes |
| `node_status` | Node CPU, memory, uptime |
| `list_vms` / `list_containers` | List QEMU VMs / LXC CTs on a node |
| `vm_status` / `ct_status` | Current status of a VM/CT |
| `vm_config` / `ct_config` | Configuration of a VM/CT |
| `list_storage` | Storage pools on a node |
| `storage_content` | Contents of a storage pool |
| `list_tasks` / `task_status` | Recent tasks / specific task status |
| `list_snapshots` | Snapshots of a VM/CT |
| `cluster_resources` | Cluster-wide resource view |
| `list_available_templates` | Downloadable appliance templates |

### Mutating (with guardrails + audit)

| Tool | Guardrails |
|------|------------|
| `create_vm` | VMID range, CPU/memory caps, storage allowlist, ISO format |
| `clone_vm` / `clone_container` | Both VMIDs validated, storage allowlist |
| `create_container` | Template format, CPU/memory caps, storage allowlist |
| `start_guest` / `restart_guest` | Protected VM check |
| `resize_disk` | Positive-only growth, per-op cap, protected VM check |
| `update_cpu_memory` | Increase-only (fetches current config), hard cap |
| `restart_networking` | Node name validation |
| `download_template` | HTTPS-only, SSRF protection via DNS resolution |

### Guest Execution

- **`run_script`** — runs pre-approved scripts (defined in config or `scripts/` directory). Safe to auto-allow in Claude Code.
- **`guest_exec`** — runs arbitrary commands inside a guest VM/CT. Each invocation triggers Claude Code's approval prompt so the human sees the exact command.

## Setup

### Prerequisites

- Python 3.11+
- Proxmox VE with API token
- libsecret (GNOME Keyring or compatible) — `apt install gir1.2-secret-1`
- PyGObject system package — `apt install python3-gi`

### Install

```bash
git clone <repo-url> && cd servermonkey
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e ".[dev]"
```

The `--system-site-packages` flag is needed for PyGObject access.

### Run interactive setup

```bash
.venv/bin/servermonkey-setup
```

The setup wizard will:
1. **Prompt for credentials** — Proxmox user (e.g. `user@pam`) and API token name, updating `config.toml` and printing the `secret-tool` command to store the token secret in your keyring.
2. **Pin the CA certificate** — Fetches the Proxmox server's TLS certificate, displays the SHA-256 fingerprint, and asks you to verify it matches what's shown on the Proxmox web UI (Datacenter > Certificates). The certificate is saved to `~/.config/servermonkey/proxmox-ca.pem`.

### Store your API token

The setup wizard prints the exact command, but here's the pattern:

```bash
secret-tool store --label="servermonkey proxmox api token" \
  application proxmox service api host your-proxmox-host.example.com
```

Paste the token value when prompted. The token is retrieved at runtime via libsecret and never touches disk.

### Register with Claude Code

```bash
cp .mcp.json.example .mcp.json
# Edit .mcp.json to set the correct path to your .venv/bin/python3
```

Or register via CLI:

```bash
claude mcp add servermonkey -- /path/to/.venv/bin/python3 -m servermonkey.server
```

Verify with `/mcp` in Claude Code to see the registered tools.

## Configuration

See `config.toml.example` for all options:

```toml
[proxmox]
host = "proxmox.example.com"
user = "servermonkey@pve"
token_name = "mcp"
ca_cert_path = "~/.config/servermonkey/proxmox-ca.pem"

[resource_caps]
max_vcpus = 8
max_memory_mb = 16384
max_disk_grow_gb = 100

[protected]
no_stop = [100, 101]    # VMIDs that can't be restarted/started
no_modify = []          # VMIDs that can't have config changed

[storage]
allowed = ["local", "local-lvm"]

[scripts]
apt-update = "apt update && apt upgrade -y"
check-dns = "resolvectl status"
```

Multi-line scripts go in the `scripts/` directory as `.sh` files and are referenced by name (e.g., `bootstrap-ubuntu` for `scripts/bootstrap-ubuntu.sh`).

### App Scripts

Application-specific scripts live in `scripts/apps/<app-name>/` subdirectories. The server discovers them automatically — no code changes needed.

```
scripts/apps/
  czkawka/
    install-czkawka.sh     # run_script(script_name="install-czkawka")
  forgejo/
    forgejo-install.sh     # run_script(script_name="forgejo-install")
    forgejo-move-repos.sh  # run_script(script_name="forgejo-move-repos")
    README.md
  matrix/
    install-matrix.sh      # run_script(script_name="install-matrix")
    install-shuri-bot.sh   # run_script(script_name="install-shuri-bot")
    README.md
  readeck/
    install-readeck.sh     # run_script(script_name="install-readeck")
```

When a script name isn't found in flat `scripts/` or config inline scripts, ServerMonkey searches `scripts/apps/*/` for a matching `.sh` file. Flat scripts take priority over app module scripts if names collide.

## Security

### What exists

- **Credentials from libsecret** — never on disk or in env vars
- **CA cert pinning** — interactive fingerprint verification, not blind TOFU
- **Input validation** — every parameter validated (regex for names, range for IDs, allowlists for storage)
- **SSRF protection** — download URLs resolved via `socket.getaddrinfo()` and checked against `ipaddress` module (catches DNS rebinding, IPv6 mapped addresses, hex/octal encoding)
- **Command path validation** — `guest_exec` requires absolute paths with no shell metacharacters
- **Shell injection prevention** — `run_script` uses `"$@"` positional parameters, not string concatenation
- **Audit trail** — atomic file creation (0600), directory permissions (0700), fcntl locking, log rotation, sensitive field redaction. Guardrails failures are logged to the audit trail (not silently dropped), providing visibility into rejected probes
- **Resource caps** — configurable limits on CPU, memory, and disk growth
- **Core dumps disabled** — `RLIMIT_CORE` set to 0 at client initialization

### What doesn't exist (by design)

- No delete operations (VMs, CTs, snapshots, backups, images)
- No stop operations (only restart; protected VMs can't even restart)
- No disk shrink (resize uses `+` prefix)
- No CPU/memory reduction (compared against current config)

## Testing

```bash
# Unit + integration tests (no network required)
.venv/bin/pytest tests/ -v --ignore=tests/test_functional.py

# Functional tests against a live Proxmox cluster
.venv/bin/pytest tests/test_functional.py -v
```

160 unit/integration tests covering guardrails validation, audit logging, credential retrieval, config schema, server integration, and SSRF bypass vectors. Functional tests in `tests/test_functional.py` validate end-to-end MCP tool execution against a live Proxmox cluster (marked with `@pytest.mark.functional`, skipped when credentials are unavailable).

## Project Structure

```
servermonkey/
  __init__.py          # Package marker
  __main__.py          # python -m servermonkey entry point
  server.py            # FastMCP server + 27 tool definitions
  client.py            # Thin proxmoxer wrapper (no delete methods)
  guardrails.py        # All validation functions
  credentials.py       # libsecret retrieval + CA cert verification
  audit.py             # JSONL audit logger with locking + rotation
  config.py            # Shared config loading + schema validation
  setup.py             # Interactive setup wizard (creds + CA cert)
scripts/               # User-defined guest scripts (.sh files)
  apps/                # App module scripts (auto-discovered subdirs)
    czkawka/           # Media dedup/organize (czkawka + FileBot in Docker)
    forgejo/           # Forgejo git server setup and migration
    matrix/            # Matrix homeserver (Continuwuity + Caddy + Shuri bot)
    readeck/           # Readeck read-it-later service
  runpod/              # RunPod GPU pod management CLI + boot scripts
skill/                 # Claude Code skill definition + workflows
tests/                 # pytest test suite (160 tests)
config.toml.example    # Configuration template
.mcp.json.example      # MCP registration template
```

## Contributing

### Adding App Modules

The easiest way to contribute is adding scripts for applications you manage on Proxmox:

1. Create a directory: `scripts/apps/<app-name>/`
2. Add scripts named `<app>-<action>.sh` (e.g., `forgejo-install.sh`)
3. Add a `README.md` documenting what each script does, expected arguments, and prerequisites
4. Scripts are auto-discovered — no changes to server code needed

See `scripts/apps/forgejo/` for an example.

### Development

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest tests/ -v --ignore=tests/test_functional.py
```

## Dependencies

Only 3 runtime dependencies:

- `mcp[cli]` — Model Context Protocol server framework
- `proxmoxer` — Proxmox VE API client
- `PyGObject` — libsecret bindings for credential retrieval
