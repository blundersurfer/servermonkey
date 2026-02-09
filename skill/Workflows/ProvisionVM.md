# Provision VM/CT Workflow

## Purpose
Create or clone VMs and containers with proper validation and sensible defaults.

## Creating a New Container (most common)

1. **Check templates**: Call `list_available_templates` to find OS templates
2. **Check storage**: Call `storage_content` on target storage to verify template is downloaded
3. **Download if needed**: Call `download_template` if the template isn't available
4. **Pick VMID**: Call `cluster_resources(resource_type="vm")` to find an unused VMID
5. **Create**: Call `create_container` with validated parameters
6. **Start**: Call `start_guest` with vm_type="lxc"
7. **Bootstrap** (optional): Call `run_script` with "bootstrap-ubuntu" or similar

## Creating a New VM

1. **Check ISOs**: Call `storage_content` to find available ISOs
2. **Pick VMID**: Same as above
3. **Create**: Call `create_vm` with ISO, memory, cores, storage
4. **Start**: Call `start_guest` with vm_type="qemu"

## Cloning

1. **Identify source**: Call `vm_config` or `ct_config` to review source
2. **Pick VMID**: Same as above
3. **Clone**: Call `clone_vm` or `clone_container`
4. **Adjust resources** (optional): Call `update_cpu_memory` if the clone needs different specs

## Defaults
- Container: 1 core, 512 MB RAM, local-lvm storage, DHCP networking
- VM: specify cores, memory, ISO, and storage explicitly

## Important
- VMIDs must be >= 100 and unique
- Storage must be on the allowlist (check config.toml)
- Resource caps are enforced (max 8 vCPUs, 16 GB RAM by default)
