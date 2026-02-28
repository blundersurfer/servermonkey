# ServerMonkey

Secure [MCP](https://modelcontextprotocol.io/) server for managing Proxmox VE infrastructure through Claude Code (or any MCP client). Credentials stay in your system keyring via libsecret — never on disk, never in environment variables.

## Features

- **27 MCP tools** for Proxmox management (15 read-only, 10 mutating, 2 guest execution)
- **libsecret credential management** — API tokens retrieved from GNOME Keyring / KDE Wallet at runtime
- **CA certificate pinning** — interactive setup with SHA-256 fingerprint verification
- **Guardrails** — input validation, resource caps, storage allowlists, protected VM enforcement
- **Audit logging** — every tool call logged to `~/.local/share/servermonkey/audit.jsonl` with file locking, rotation, and sensitive field redaction
- **Tiered guest execution** — pre-approved scripts run freely; arbitrary commands require human approval via Claude Code's permission system
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

### Store your API token

```bash
secret-tool store --label="devai proxmox api token" \
  application proxmox service api host your-proxmox-host.example.com
```

Paste the token value when prompted. The token is retrieved at runtime via libsecret and never touches disk.

### Configure

```bash
cp config.toml.example config.toml
# Edit config.toml with your Proxmox host, user, token name, and preferences
```

### Run interactive setup

```bash
.venv/bin/servermonkey-setup
```

The setup wizard will:
1. **Prompt for credentials** — Proxmox user (e.g. `user@pam`) and API token name, updating `config.toml` and printing the `secret-tool` command to store the token secret in your keyring.
2. **Pin the CA certificate** — Fetches the Proxmox server's TLS certificate, displays the SHA-256 fingerprint, and asks you to verify it matches what's shown on the Proxmox web UI (Datacenter > Certificates). The certificate is saved to `~/.config/servermonkey/proxmox-ca.pem`.

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
.venv/bin/pytest tests/ -v

# Functional tests against a live Proxmox cluster
.venv/bin/pytest tests/test_functional.py -v
```

154 unit/integration tests covering guardrails validation, audit logging, credential retrieval, config schema, server integration, and SSRF bypass vectors. Functional tests in `tests/test_functional.py` validate end-to-end MCP tool execution against a live Proxmox cluster (marked with `@pytest.mark.functional`, skipped when credentials are unavailable).

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
  setup.py             # Interactive CA cert provisioning
scripts/               # User-defined guest scripts (.sh files)
skill/                 # Claude Code skill definition + workflows
tests/                 # pytest test suite
config.toml.example    # Configuration template
.mcp.json.example      # MCP registration template
```

## Dependencies

Only 3 runtime dependencies:

- `mcp[cli]` — Model Context Protocol server framework
- `proxmoxer` — Proxmox VE API client
- `PyGObject` — libsecret bindings for credential retrieval
