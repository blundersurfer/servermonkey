# servermonkey — Backlog

> Enhancement notes for the MCP. Surfaced from real lab/homelab use cases that
> hit gaps in the current toolset.

---

## TODO: expose `pct set --features` for LXC bootstrap

**Surfaced:** 2026-04-30 during ai-lab `lab-004-grader` container provisioning
(vmid 511 on eshu).

**Problem:** the `create_container` MCP tool doesn't expose Proxmox's
`pct set <vmid> --features <list>` parameter. Default LXC creation lands
without `nesting=1` — which means systemd inside the container can't access
the host's cgroup/namespace primitives, and `systemctl` operations fail with:

```
System has not been booted with systemd as init system (PID 1). Can't operate.
Failed to connect to bus: Host is down
```

That breaks every install script that does `systemctl enable`, `systemctl start`,
or otherwise touches the init layer — including the canonical
`apt-get install openssh-server && systemctl enable --now ssh` pattern. SSH
service can't be brought up reliably until features are corrected.

**Workaround currently:** SSH to the host and run `pct stop && pct set --features
nesting=1,keyctl=1 && pct start` manually. This is exactly the kind of step the
MCP exists to abstract.

**Proposed enhancement:**

1. **Add a `features` param to `create_container`.** Accept a comma-separated
   list (e.g., `"nesting=1,keyctl=1"`) and pass through to the Proxmox API's
   `pct create --features` field. **Default this to `nesting=1,keyctl=1`** for
   LXC creation, since 90%+ of useful provisioning depends on systemd working.
2. **Add a `set_container_features` (or general `update_container_config`) tool**
   that wraps `pct set --features ...` for already-existing containers, with a
   stop/start workflow handled internally.

**Why nesting=1,keyctl=1 specifically:**
- `nesting=1`: enables nested cgroups + namespaces; required for systemd inside
  unprivileged LXC. Allows containers to run as VMs do.
- `keyctl=1`: enables Linux kernel keyrings (needed by systemd-cryptsetup, some
  apt operations, GPG-related workflows). Cheap to enable; some workloads break
  without it.

**Acceptance:** an MCP `create_container` call with no extra params produces a
container in which `systemctl is-active ssh` can succeed after `apt-get install
openssh-server && systemctl enable --now ssh`.

**Related:** the `pre-vetted install script` pattern (see `scripts/apps/lab-004-grader/`)
is also a good candidate for this enhancement — once nesting is on by default,
the install script's SSH section works first-time.

---

## TODO: expose general LXC command execution (analog to `guest_exec` for VMs)

**Surfaced:** 2026-04-30 during the same ai-lab provisioning workflow.

**Problem:** `guest_exec` and `run_script` route through Proxmox's
`POST /nodes/{node}/lxc/{vmid}/agent/exec` endpoint, which is **QEMU Guest Agent
only** — it returns `501 Not Implemented` for LXC containers. There's no
arbitrary-command-execution path for LXCs through the MCP.

The Proxmox REST API itself doesn't expose `pct exec` directly, but the
equivalent functionality is achievable by:

- SSH-ing to the Proxmox node and running `pct exec <vmid> -- <cmd>`, OR
- Once SSH is set up inside the LXC, talking to the LXC directly

**Workaround currently:** ask the human to run `pct exec` from a host shell
(or pipe a script via `cat script | ssh root@host pct exec <vmid> -- bash`).
This is the path I had to fall back to during the lab-004-grader bootstrap.

**Proposed enhancement:**

1. **Add an `lxc_exec` tool** that SSHs to the Proxmox node (using the MCP's
   existing host credentials) and runs `pct exec <vmid> -- <cmd>` from there.
   Mirror the same human-approval flow as `guest_exec`.
2. **Or**, alternatively, add an `lxc_push_and_exec` tool that:
   - Takes a script body or path
   - Pushes via `pct push <vmid> <local> <remote>`
   - Runs via `pct exec <vmid> -- bash <remote>`
   - Cleans up

**Acceptance:** a single MCP call provisions an LXC end-to-end without the user
ever opening a host shell. Combined with the `features` enhancement above, the
full lab-004-grader bootstrap becomes:

```
create_container(features="nesting=1,keyctl=1", ...)  # systemd works
start_guest(...)
lxc_exec(script="lab-004-grader-install")  # SSH up, key authorized, toolchains in
ssh root@<container-ip>  # works directly
```

That's the workflow we tried for and couldn't complete on 2026-04-30 with the
current MCP.

---

## How to use this file

When a homelab/lab task hits an MCP gap, append a TODO entry here with:
- **Surfaced:** date and originating workflow
- **Problem:** specific failure mode + any error output
- **Workaround currently:** what we did instead
- **Proposed enhancement:** concrete tool addition or change
- **Acceptance:** how we'd know the enhancement worked

Promote items from here to the project's actual issue tracker (forgejo) when
prioritized.
