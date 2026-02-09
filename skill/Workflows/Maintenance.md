# Maintenance Workflow

## Purpose
Common maintenance tasks: resizing, scaling, template management, and running scripts on guests.

## Resize Disk

1. **Check current config**: Call `vm_config` or `ct_config` to see current disk sizes
2. **Resize**: Call `resize_disk` with positive growth amount
3. **Verify**: Inside the guest, the filesystem may need expanding — use `run_script` with "check-disk" or `guest_exec` to run `resize2fs`

### Important
- Disk can only grow, never shrink
- Max growth per operation is configurable (default 100 GB)
- Protected VMs (no_modify list) cannot be resized

## Scale CPU/Memory

1. **Check current**: Call `vm_config` or `ct_config`
2. **Update**: Call `update_cpu_memory` with new values
3. **Restart** (for VMs): CPU/memory changes on QEMU VMs typically require a restart to take effect. Call `restart_guest`.

### Important
- Only increases allowed — cannot reduce CPU or memory
- Max 8 vCPUs and 16 GB RAM by default (configurable in config.toml)

## Run Scripts on Guests

### Pre-approved scripts (no approval needed)
```
run_script(node="eshu", vmid=105, vm_type="lxc", script_name="apt-update")
run_script(node="eshu", vmid=105, vm_type="lxc", script_name="check-disk")
run_script(node="eshu", vmid=105, vm_type="lxc", script_name="bootstrap-ubuntu")
```

### Ad-hoc commands (requires human approval)
```
guest_exec(node="eshu", vmid=105, vm_type="lxc", command="systemctl", args=["status", "nginx"])
```

## Template Management

1. **List available**: Call `list_available_templates` to see what's available to download
2. **Check downloaded**: Call `storage_content` to see what's already on storage
3. **Download**: Call `download_template` with storage and content_type
