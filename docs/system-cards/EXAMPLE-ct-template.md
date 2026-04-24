# System Card: CT 999 — example-app

> **Template card.** Copy this file, rename to `ct<id>-<hostname>.md`, and fill in real values.
> Real cards in this directory are gitignored — only `EXAMPLE-*.md` ships publicly.

## Overview

| Field | Value |
|-------|-------|
| **VMID** | 999 |
| **Hostname** | example-app |
| **Purpose** | One-line description of what this container is for |
| **Node** | <node-name> |
| **Status** | Created / Bootstrapped / In service / Decommissioned |
| **Created via** | ServerMonkey `create_container` on YYYY-MM-DD |

## Container Specifications

| Resource | Value |
|----------|-------|
| **Base Image** | `local:vztmpl/debian_12.tar` (Debian 12 Bookworm) |
| **CPU Cores** | 2 |
| **RAM** | 2048 MB |
| **Disk** | 16 GB (4 GB default + 12 GB resize) |
| **Storage** | local-lvm |
| **Network** | `name=eth0,bridge=vmbr0,tag=<vlan>,ip=dhcp` |
| **SSH Keys** | `<user>@<host>` (operator), `<agent>@<host>` (agent) |
| **Init System** | systemd |

## Application

### \<App Name\> v\<X.Y.Z\>

**What it is:** One paragraph — what the application does, how it's used in this homelab, what problem it solves.

**Why \<App\> over alternatives:**

| Option | Verdict | Reasoning |
|--------|---------|-----------|
| **\<App\>** | **Selected** | Why this won — feature, ergonomics, maintenance, fit |
| Alternative A | Rejected | Why not |
| Alternative B | Considered | Tradeoff or constraint that ruled it out |
| Alternative C | Rejected | Operational complexity, license, scope |

## Bootstrap Procedure

1. ServerMonkey provisions the container (`create_container` with above specs)
2. Manually set VLAN tag and inject SSH keys (`vmbr0` bridge, tag `<vlan>`)
3. SSH in, run install script (`scripts/apps/<app>/install-<app>.sh`)
4. Configure application-specific settings (DB, auth, integrations)
5. Test: `<smoke-test command>`
6. Document any per-deployment quirks below

## Operator Notes

- **Backup posture:** \<how this container's data is protected — snapshots, off-host backups, recovery RPO/RTO\>
- **Monitoring:** \<what tells you when it's broken — health-check URL, log location, metrics endpoint\>
- **Known caveats:** \<anything future-you needs to remember — quirks, manual steps, gotchas\>
- **Integration points:** \<what other services depend on this, or what this depends on\>

## Change log

| Date | Change | Notes |
|------|--------|-------|
| YYYY-MM-DD | Created | Initial provisioning |
