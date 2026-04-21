# ServerMonkey

Secure [MCP](https://modelcontextprotocol.io/) server that gives AI agents safe, audited access to Proxmox VE infrastructure — with destruction made impossible by design.


## Why I built this

I have a lot of ideas and not a lot of time. IT Ops is a tediious process of testing and failure leading to eventual sucess. That's great if I want to learn, but terrible if it's just a sidequest to doing something else. This MCP is meant to solve that problem. Make managing my infrastructure easy without building a footgun. It's got to be 
1. Actually useful
2. Safe enough
3. Be transparent enough that I can see tarpits I'm walking into

I have a firewall and segemented network, family services like backups, photo managmenet, media servers, internal CA, etc. Lab services like git, proxmox vms, conatiners, and microvms, VM and container images, AI resources  and oather stuff. Failure in the wrong area can mean losing decades of family photos, the network going down on an important work meeting, or losing months of research. So, I've essetnally got my own personal Prod.

## Context

ServerMonkey is the Proxmox access layer for my personal homelab. My lab is sprawling and haphazard and has many projects sitting inthe backlog due to a lack of energy or enthusiasm. Now that I've got my shiny robot to lower the activation enery for projects I need a way to spin up the resoures I need when I need it. That meant handing my aassisnt a Proxmox API token with enough power to get stuff done, but not rm -rf my lab.

## How I use this and my biases

1. Start with a planning session with your favourite robot
2. Make sure to discuss what options there are for your usecae. Check what's the state of the art, what's popular, what's mainatined etc. When possible I personally avoid 
  1. Immature or experimental applications and projects
  2. Projects that aren't maintained anymore
  3. Projects that are not widely used
  4. Anytyhing that smells off.
5. Use planning mode to cover the installation process
6. Review your plan for architectural and security issues
7. Finally deploy the base template
8. Manually tweak any settings you need. (Bootstrapping SSH, setting VLAN tags)
9. Make sure the robot can access the conainter/vm, etc to configure the rest of the services.
10. Testing that everything works

It seems like a lot but I'd rather be more invlved and move slower if it means I don't need to worry aobut my entire homelab disappearing becuase of a clever robot.


## Secrity Thoughts:
1. Keep everything sketchy on it's own subnet. This means the permissions don't allow changing the vlan tags
2. Don't give permissions to the robot to destroy resoruces. If you need to burn something down type the commands yourself.
3. Don't give permissions to stop resource. This one is opinoinated. I'd rather have too much running than have something I need stop.
4. Don't touch files you shoudln't. The robot can't delete or write to file spaces it shoudln't
5. Core services are segemnted on a differnt device. Because I'm paranoid this Proxmox node is specically for playing with, not core services
6. I want to know what is done by the robot. Containers and VM's use it's own number space YXX. IAM roles are named appropriately "sa-name". SMB mountpoints are created per app with scoped access tokens for the required proxmox roles.


## The Problem

AI agents are increasingly capable of managing infrastructure: provisioning VMs, scaling resources, deploying services. But giving an agent API access to a hypervisor is giving it the keys to every machine you own. A single prompt injection, a misunderstood instruction, or an overly ambitious plan can delete VMs, wipe backups, or exfiltrate credentials — and the agent will do it confidently, without hesitation.

The standard approach is to add confirmation prompts and hope the human catches the dangerous ones. ServerMonkey takes a different position: **make destructive operations impossible, not just inconvenient.** There is no delete tool to misuse. There is no stop command to invoke. The attack surface isn't minimized — it's absent.

## Design Philosophy

ServerMonkey is built on a principle borrowed from safety-critical systems engineering: **if a failure mode is unacceptable, don't mitigate it — eliminate the mechanism entirely.**

- **No delete operations exist.** Not behind a flag, not with confirmation. The client has no method, the server has no tool, the API call is never constructed. You cannot delete a VM, container, snapshot, backup, or disk image through ServerMonkey. Deletion remains a human-only operation performed through the Proxmox web UI.
- **No stop operations exist.** A misbehaving agent cannot shut down production services. Restart is available (with protected-VM enforcement), but stop is not.
- **Resources only grow.** Disk resize uses a `+` prefix (enforced at the API call layer). CPU and memory changes compare against current config and reject reductions. An agent can scale up to handle load; it cannot starve a workload.
- **Credentials never touch disk.** API tokens live in the system keyring (libsecret/GNOME Keyring) and are retrieved at runtime. No `.env` files to leak, no config values to commit, no environment variables for other processes to read.

## Security Architecture

Security is enforced across five independent layers. Compromising one layer does not compromise the system — each layer assumes the others may fail.

```
┌─────────────────────────────────────────────────┐
│  Layer 5: MCP Permission System                 │
│  Claude Code prompts for human approval on       │
│  arbitrary command execution (guest_exec)         │
├─────────────────────────────────────────────────┤
│  Layer 4: Audit Trail                           │
│  Every tool call logged — success and failure — │
│  with credential redaction in logs AND responses │
├─────────────────────────────────────────────────┤
│  Layer 3: Client API Surface                    │
│  No delete/stop methods exist in the client     │
│  class. Can't call what isn't there.            │
├─────────────────────────────────────────────────┤
│  Layer 2: Guardrails Module                     │
│  Input validation, resource caps, protected VM  │
│  enforcement, storage allowlists — all checked  │
│  before any API call is made                    │
├─────────────────────────────────────────────────┤
│  Layer 1: Configuration                         │
│  Resource limits, protected VM lists, storage   │
│  allowlists — all externalized to config.toml   │
└─────────────────────────────────────────────────┘
```

### Layer 1: Configuration-Driven Constraints

All security boundaries are defined in `config.toml`, not hardcoded. This means the operator (you) decides what the agent can do — and those boundaries are enforced at every layer above.

- **Resource caps**: maximum vCPUs, memory, and disk growth per operation
- **Protected VMs**: lists of VMIDs that cannot be restarted, modified, or have commands executed inside them
- **Storage allowlists**: which storage pools the agent can provision to
- **VMID ranges**: valid ID ranges for new guests

### Layer 2: Input Validation (Guardrails)

Every parameter to every tool is validated before it reaches the Proxmox API. This is the primary defense against prompt injection attacks that attempt to manipulate tool arguments:

- **Node names**: hostname-safe regex, preventing path traversal
- **VMIDs**: range-checked integers, rejecting negative values and overflows
- **Disk names**: strict Proxmox format validation
- **Template paths**: character allowlist preventing injection
- **Script names**: alphanumeric + hyphen/underscore only, preventing directory traversal
- **Command paths**: absolute paths with no shell metacharacters (`guest_exec`)
- **SSH keys**: type-prefix and format validation
- **Download URLs**: HTTPS-only with SSRF protection (see Threat Model)

### Layer 3: Reduced API Surface

The Proxmox client class (`client.py`) is a thin wrapper around the proxmoxer SDK — but it only exposes read and create operations. There are no methods for:
- Deleting VMs, containers, snapshots, or disk images
- Stopping VMs or containers
- Shrinking disks or reducing CPU/memory

This isn't a policy decision enforced at a higher layer — the code to perform these operations does not exist. An agent exploring available methods through introspection or error probing will find nothing to exploit.

### Layer 4: Audit Trail

Every tool invocation is logged to `~/.local/share/servermonkey/audit.jsonl` — including calls that fail validation. This serves two purposes: forensic accountability and attack detection.

- **Atomic file creation** with 0600 permissions from the first byte (no race between create and chmod)
- **fcntl file locking** for concurrent write safety
- **Automatic rotation** at 10 MB
- **Credential redaction** applied to both the audit log entry AND the tool response returned to the AI agent — preventing credential harvesting through API responses
- **Sensitive field scrubbing**: any parameter named password, token, secret, or key is replaced with `[REDACTED]`
- **Guardrail failures are logged**, not silently dropped — providing visibility into rejected probes

The dual-redaction design (log + response) is an AI-specific security control: even if an API response contains credentials, the agent never sees them.

### Layer 5: Human-in-the-Loop Execution

ServerMonkey implements tiered guest execution that leverages MCP's built-in permission system:

- **`run_script`**: executes pre-approved scripts defined in config or the `scripts/` directory. Arguments are passed via shell positional parameters (`"$@"`), never string concatenation. Safe to auto-allow.
- **`guest_exec`**: executes arbitrary commands inside a guest VM/CT. Each invocation triggers Claude Code's approval prompt, so the human sees and approves the exact command before execution.

This creates a natural separation: routine operations flow freely, while novel commands require human judgment.

## Threat Model

ServerMonkey is designed to defend against these attack scenarios:

| Threat | Attack Vector | Defense |
|--------|--------------|---------|
| **Prompt injection → infrastructure damage** | Malicious content in a webpage/document tricks the agent into deleting VMs | Delete operations don't exist. No amount of prompt manipulation can invoke a nonexistent tool. |
| **Credential exfiltration via tool responses** | Agent extracts API tokens from Proxmox API responses | Dual redaction: credentials scrubbed from audit logs AND tool responses before the agent sees them. |
| **SSRF via template download** | Agent is tricked into downloading from internal IPs | URL validation resolves hostnames via `socket.getaddrinfo()`, checks ALL returned addresses against private/loopback/link-local ranges. Catches DNS rebinding, IPv6-mapped addresses, hex/octal encoding. HTTPS-only. |
| **Shell injection via guest execution** | Crafted arguments to `run_script` or `guest_exec` | `run_script` uses `"$@"` positional parameters. `guest_exec` requires absolute paths, rejects shell metacharacters, validates via strict regex. |
| **Path traversal via script names** | `../../etc/passwd` as script name | Script names validated against `^[a-zA-Z0-9_-]+$` — no path separators possible. |
| **Resource exhaustion** | Agent provisions excessive infrastructure | Config-driven caps on CPU, memory, disk growth. Per-operation limits, not just totals. |
| **Modification of critical infrastructure** | Agent reconfigures production VMs | Protected VM lists (no_stop, no_modify, no_exec) enforced at guardrails layer. |
| **Credential leakage via core dumps** | Process crash dumps contain API token | `RLIMIT_CORE` set to 0 (hard and soft) at client initialization. |
| **Credential leakage via environment** | Other processes read API token from env | Credentials retrieved from libsecret at runtime, never stored in environment variables or files. |

## Design Decisions

These are deliberate tradeoffs, not oversights:

**No delete, rather than delete-with-confirmation.** Confirmation dialogs are a weak control — they depend on a human reading carefully every time. For an AI agent, "confirm" is just another tool call. Removing the capability entirely eliminates the category of failure.

**Increase-only resources, rather than bidirectional with validation.** Scaling down is a destructive operation in disguise — shrinking a disk can corrupt a filesystem, reducing memory can OOM a workload. By making resources monotonically increasing, the worst case is over-provisioning, which is recoverable.

**libsecret over environment variables.** Environment variables are readable by any process running as the same user, visible in `/proc/[pid]/environ`, and trivially leaked by an agent that runs `env` or `printenv`. libsecret (GNOME Keyring / KDE Wallet) provides encrypted storage with process-level access control. The credential exists in memory only during API calls.

**Tiered execution over blanket allow/deny.** A binary choice between "agent can run commands" and "agent cannot run commands" is too coarse. Pre-approved scripts handle 90% of operational needs; human approval handles the rest. This mirrors the principle of least privilege without sacrificing utility.

**SSRF protection via DNS resolution, not URL regex.** URL pattern matching is trivially bypassed (decimal IPs, IPv6 encoding, DNS rebinding). ServerMonkey resolves the hostname and checks every returned IP address against RFC 1918/5737/6598 ranges, catching attacks that regex-based filters miss.

The actual check, from `servermonkey/guardrails.py`:

```python
def _is_private_ip(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved


def validate_download_url(url: str) -> None:
    """HTTPS-only; ALL resolved IPs must be public."""
    parsed = urlparse(url)
    # ... scheme + hostname checks ...
    addrinfo = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    for family, _type, _proto, _canonname, sockaddr in addrinfo:
        if _is_private_ip(sockaddr[0]):
            raise ValueError(f"URL hostname resolves to private address: {hostname!r} -> {sockaddr[0]}")
```

Every resolved IP is checked, not just the first — which defeats DNS rebinding, IPv6-mapped IPv4 (`::ffff:10.0.0.1`), and hex/octal/decimal encodings in one pass.

## Why not alternatives?

<!-- REVIEW: Draft comparisons below. Edit each to match your actual evaluation. These are the three most-asked reviewer questions; leaving them unanswered looks like you didn't consider them. -->

**Why not Proxmox CLI + sudoers restrictions?** The obvious approach: constrain what commands an agent can run over SSH. In practice, building a sudoers policy that permits "clone VM from template" while forbidding "delete VM" requires parsing `qm` arguments in a shell regex, which is exactly the pattern-matching approach guardrails.py replaces. Worse, SSH-as-API makes every operation a shell-injection opportunity. A Python guardrails module is auditable; a sudoers regex is not.

**Why not Ansible?** Ansible is declarative and stateful — the wrong fit for agent-driven, ad-hoc operations. An agent asking "is VM 504 running?" shouldn't trigger a playbook run. Ansible also has no concept of "forbidden operations" — any task can be written into a playbook, and delete lives alongside create. The structural asymmetry (no delete methods exist) is easier to enforce at an MCP boundary than inside Ansible.

**Why not raw Proxmox REST API with a scoped token?** Proxmox tokens can be privilege-scoped, but the granularity stops at roles like `PVEVMAdmin` — which includes delete. There's no "PVEVMAdmin without destroy" role. A tighter role can't be synthesized without an intermediate service; that service is this one.

<!-- REVIEW: If you've evaluated other options (Terraform, Packer, Proxmox-as-a-Service platforms), add them. Three is the floor, not the ceiling. -->

## Tools

27 MCP tools organized by risk level:

### Read-Only (15 tools)

| Tool | Purpose |
|------|---------|
| `list_nodes` / `node_status` | Discover cluster nodes and check health |
| `list_vms` / `list_containers` | Inventory guests on a node |
| `vm_status` / `ct_status` | Current state of a specific guest |
| `vm_config` / `ct_config` | Configuration of a specific guest |
| `ct_interfaces` | Network interfaces of a container |
| `list_storage` / `storage_content` | Storage pools and their contents |
| `list_tasks` / `task_status` | Proxmox task history |
| `list_snapshots` | Snapshots of a guest |
| `cluster_resources` | Cluster-wide resource overview |
| `list_available_templates` | Downloadable appliance templates |

### Mutating (10 tools — all guarded)

| Tool | Guardrails Applied |
|------|--------------------|
| `create_vm` | VMID range, CPU/memory caps, storage allowlist, ISO format |
| `create_container` | Template format, CPU/memory caps, storage allowlist |
| `clone_vm` / `clone_container` | Both VMIDs validated, storage allowlist |
| `start_guest` / `restart_guest` | Protected VM enforcement |
| `resize_disk` | Positive-only growth, per-operation cap, protected VM check |
| `update_cpu_memory` | Increase-only (compared against current config), hard caps |
| `restart_networking` | Node name validation |
| `download_template` | HTTPS-only, full SSRF protection |

### Guest Execution (2 tools — tiered)

| Tool | Permission Model |
|------|-----------------|
| `run_script` | Pre-approved scripts only. Auto-allowable. |
| `guest_exec` | Arbitrary commands. Requires human approval per invocation. |

## System Cards

Each deployed container and VM has a **system card** in `docs/system-cards/` — a single document describing what's running, why this software was selected over alternatives, resource sizing, network topology, and the bootstrap procedure. System cards are the operator-readable counterpart to ServerMonkey's machine-enforced guardrails: guardrails tell the *agent* what it can do, system cards tell *humans* what exists and why.

Current system cards:

- [`ct507-wiki.md`](docs/system-cards/ct507-wiki.md) — Wiki.js personal knowledge base
- [`ct508-vecdb.md`](docs/system-cards/ct508-vecdb.md) — PostgreSQL + pgvector AI memory layer

<!-- REVIEW: If you add/retire containers, keep this list current. If you have more system cards than two, list them all or just say "see docs/system-cards/". -->

## Example Session

<!-- REVIEW: This is a plausible transcript but not a real one. Either (a) record a real session via asciinema and replace, or (b) mark this as illustrative. Real transcripts are more persuasive. -->

```
You: "Provision a small Debian 12 container on node eshu for a pihole instance. Call it dns-test, give it 1 GB RAM, 8 GB disk."
Shuri: [calls list_available_templates]
       Debian 12 template is available on local storage.
       [calls create_container: vmid=513, node=eshu, template=debian_12, memory=1024, disk=8]
       Created CT 513 on eshu. Storage: local-lvm. Protected-list: no.

You: "Actually, delete it — wrong subnet."
Shuri: ServerMonkey doesn't expose a delete tool. To remove CT 513, use the Proxmox web UI at https://eshu.local:8006 → Datacenter → eshu → CT 513 → More → Remove. I can stop the container from being started again, but the delete is a human operation.
```

The "delete refusal" behavior is structural, not a policy layer — the `delete` method does not exist on `Proxmox` client, so the tool can't be invoked. An agent probing for deletion capabilities finds nothing to exploit.

## Testing

162 unit and integration tests covering:

- **Guardrails validation**: every input validator, every edge case, every bypass attempt
- **Audit logging**: file permissions, locking, rotation, redaction patterns, session tracking
- **Credential retrieval**: libsecret integration, error paths
- **Config schema**: required sections, type validation, range enforcement
- **Server integration**: tool wiring, error propagation
- **SSRF bypass vectors**: localhost, private IPs, IPv6-mapped, link-local, DNS resolution failures
- **Functional tests**: end-to-end MCP tool execution against a live Proxmox cluster (skipped when credentials unavailable)

```bash
# Unit + integration tests
.venv/bin/pytest tests/ -v --ignore=tests/test_functional.py

# Functional tests (requires Proxmox credentials in keyring)
.venv/bin/pytest tests/test_functional.py -v
```

## Setup

### Prerequisites

- Python 3.11+
- Proxmox VE with API token ([creating tokens](https://pve.proxmox.com/wiki/User_Management#pveum_tokens))
- libsecret — `apt install gir1.2-secret-1`
- PyGObject — `apt install python3-gi`

### Install

```bash
git clone <repo-url> && cd servermonkey
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e ".[dev]"
```

The `--system-site-packages` flag is required for PyGObject access.

### Interactive Setup

```bash
.venv/bin/servermonkey-setup
```

The setup wizard will:
1. Prompt for Proxmox credentials and update `config.toml`
2. Print the `secret-tool` command to store the API token in your keyring
3. Fetch and pin the Proxmox CA certificate with SHA-256 fingerprint verification

### Store Your API Token

```bash
secret-tool store --label="servermonkey proxmox api token" \
  application proxmox service api host your-proxmox-host.example.com
```

### Register with Your MCP Client

```bash
# Copy and edit the example config
cp .mcp.json.example .mcp.json

# Or register via Claude Code CLI
claude mcp add servermonkey -- /path/to/.venv/bin/python3 -m servermonkey.server
```

## Configuration

All security boundaries are operator-defined in `config.toml`:

```toml
[proxmox]
host = "proxmox.example.com"
user = "servermonkey@pve"
token_name = "mcp"
ca_cert_path = "~/.config/servermonkey/proxmox-ca.pem"

[resource_caps]
max_vcpus = 8               # Per-operation CPU cap
max_memory_mb = 16384        # Per-operation memory cap
max_disk_grow_gb = 100       # Per-operation disk growth cap

[protected]
no_stop = [100, 101]         # VMIDs that cannot be restarted
no_modify = []               # VMIDs that cannot be reconfigured
no_exec = []                 # VMIDs that cannot have commands run inside them

[storage]
allowed = ["local", "local-lvm"]   # Storage pools the agent can use

[scripts]
apt-update = "apt update && apt upgrade -y"
check-dns = "resolvectl status"
```

### App Scripts

Application management scripts are auto-discovered from `scripts/apps/` subdirectories — no code changes needed to add new ones:

```
scripts/apps/
  czkawka/          # Media deduplication
  forgejo/          # Git server setup and migration
  matrix/           # Matrix homeserver + bot deployment
  readeck/          # Read-it-later service
```

## Project Structure

```
servermonkey/
  server.py            # FastMCP server — 27 tool definitions
  client.py            # Proxmox API wrapper (no delete/stop methods)
  guardrails.py        # Input validation + resource enforcement
  credentials.py       # libsecret retrieval + CA cert verification
  audit.py             # JSONL audit logger with locking + redaction
  config.py            # Config loading + schema validation
  setup.py             # Interactive setup wizard
scripts/               # Pre-approved guest scripts
  apps/                # Auto-discovered app module scripts
tests/                 # 160 tests
```

## Built with AI-augmented engineering

This codebase was built by me with Claude (via Claude Code) as an implementation partner. The thesis, threat model, architectural decisions, and security tradeoffs are mine; Claude is an accelerant for implementation, test generation, and iteration on specification. The result is a codebase where every non-trivial design choice — the structural absence of delete operations, the DNS-resolution-based SSRF check, the dual-redaction audit layer — originated from human reasoning about this system's failure modes.

<!-- REVIEW: If you want to go further, link to a docs/methodology.md explaining your agent-augmented workflow. AI labs actively want to see thoughtful use of AI-assisted engineering — this is positive signal, not concession. -->

## Related Work

- [Model Context Protocol](https://modelcontextprotocol.io/) — Anthropic's open standard for connecting AI agents to tools and data sources. ServerMonkey is designed against the MCP specification and Anthropic's tool-use best practices.
- [Proxmox VE](https://www.proxmox.com/en/proxmox-virtual-environment/overview) — the hypervisor this server manages.
- [proxmoxer](https://github.com/proxmoxer/proxmoxer) — the Python Proxmox SDK ServerMonkey wraps.

<!-- REVIEW: Add links to any security research or prior art that influenced the design (e.g., capability-based security papers, similar agent-safety projects). -->


## Dependencies

Three runtime dependencies, deliberately minimal:

| Package | Purpose |
|---------|---------|
| `mcp[cli]` | Model Context Protocol server framework |
| `proxmoxer` | Proxmox VE API client |
| `PyGObject` | libsecret bindings for credential retrieval |

## License

[Apache 2.0](LICENSE) — patent grant included, appropriate for security-sensitive infrastructure tooling.
