# Forgejo

Self-hosted lightweight Git service ([forgejo.org](https://forgejo.org)).

## Prerequisites

- Debian 12 (Bookworm) LXC container
- Root access
- Network connectivity (downloads binary from codeberg.org)

## Scripts

| Script | Description |
|--------|-------------|
| `forgejo-install` | Install Forgejo with PostgreSQL on a fresh Debian 12 LXC container |
| `forgejo-move-repos` | Move Forgejo repository storage to a new filesystem path |

## Usage

Via the ServerMonkey `run_script` MCP tool:

```
run_script(node="pve1", vmid=200, vm_type="lxc", script_name="forgejo-install")
```

Move repositories to a new path:

```
run_script(node="pve1", vmid=200, vm_type="lxc",
           script_name="forgejo-move-repos",
           args=["/mnt/storage/forgejo-repos"])
```

## After Installation

1. Visit `http://<container-ip>:3000/` to complete web setup
2. Create your admin account
3. Service management: `service forgejo {start|stop|restart|status}`
