# ServerMonkey — Proxmox Infrastructure Management

## Description
Manage Proxmox VE infrastructure through secure MCP tools. Provision VMs and containers, check cluster health, resize resources, and run maintenance scripts — all with guardrails, audit logging, and libsecret credential management.

## Activation
Use when the user asks about: Proxmox, VMs, containers, LXC, cluster status, provisioning, infrastructure, server management, or refers to specific VMIDs or node names.

## Available Workflows

### Status Check
Check cluster health: node status, running VMs/CTs, resource usage, recent tasks.
See: `Workflows/StatusCheck.md`

### Provision VM/CT
Create or clone VMs and containers with validated parameters.
See: `Workflows/ProvisionVM.md`

### Maintenance
Resize disks, scale CPU/memory, manage templates, run scripts on guests.
See: `Workflows/Maintenance.md`

## Key Constraints
- **No delete operations** — VMs, CTs, snapshots, and backups cannot be deleted
- **No stop operations** — only restart (and protected VMs can't even restart)
- **No shrink** — disk resize is grow-only, CPU/memory changes are increase-only
- **Storage allowlist** — only configured storage pools can be used
- **Resource caps** — max vCPUs, memory, and disk growth per operation
- **Protected VMs** — certain VMIDs cannot be restarted or modified
- **Audit trail** — every tool call is logged to `~/.local/share/servermonkey/audit.jsonl`

## Tools Quick Reference

### Read-Only
`list_nodes`, `node_status`, `list_vms`, `list_containers`, `vm_status`, `ct_status`, `vm_config`, `ct_config`, `list_storage`, `storage_content`, `list_tasks`, `task_status`, `list_snapshots`, `cluster_resources`, `list_available_templates`

### Mutating
`create_vm`, `clone_vm`, `create_container`, `clone_container`, `start_guest`, `restart_guest`, `resize_disk`, `update_cpu_memory`, `restart_networking`, `download_template`

### Guest Execution
- `run_script` — pre-approved scripts only (safe to auto-allow)
- `guest_exec` — arbitrary commands (requires human approval each time)
