# lab-004-grader scripts

Pre-vetted scripts for the H-COMPLEXITY pilot's Proxmox grading container.

## Container

- **Node:** eshu
- **vmid:** 511
- **hostname:** lab-004-grader
- **template:** Ubuntu 24.04 LTS (`local:vztmpl/ubuntu_24.04.tar`)
- **resources:** 1 vCPU, 1 GB RAM, 4 GB disk
- **purpose:** language-agnostic grader execution environment for the
  H-COMPLEXITY pilot (`research/model-fitness-benchmark/runs/2026-04-29-h-complexity-pilot/`)
  in the ai-lab repo

## Scripts

### `lab-004-grader-install`

Provisions the container with all 5 grader toolchains, enables openssh-server
with the shuri@nabu public key authorized for root login, and verifies each
toolchain's version. Idempotent — safe to re-run on an already-provisioned
container.

Toolchains installed:
- `python3` (stdlib http.server)
- `openjdk-17-jdk-headless` (com.sun.net.httpserver.HttpServer)
- `gcc` + `libmicrohttpd-dev` (libmicrohttpd)
- `gcc` alone for POSIX sockets variant
- Bun (via curl install script, symlinked to `/usr/local/bin/bun`)

Run via the servermonkey MCP:

```
mcp__servermonkey__run_script(
    node="eshu",
    vmid=511,
    vm_type="lxc",
    script_name="lab-004-grader-install"
)
```

Or directly on eshu:

```
pct exec 511 -- bash /path/to/lab-004-grader-install.sh
```

## SSH access

After install, the container accepts key-based root login from the coordinator
machine (where `~/.ssh/shuri` is the matching private key). Get the container
IP:

```
mcp__servermonkey__ct_interfaces(node="eshu", vmid=511)
```

Then from the coordinator:

```
ssh -i ~/.ssh/shuri root@<container-ip>
```

Password auth is disabled. Root login is `prohibit-password` (key-only).

## Maintenance

If the shuri@nabu key rotates, update `SHURI_PUBKEY` in `lab-004-grader-install.sh`
and re-run the script — the install is idempotent and will append the new key
without overwriting existing authorized keys.
