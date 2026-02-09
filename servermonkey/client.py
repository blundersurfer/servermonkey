"""Thin proxmoxer wrapper. NO delete methods exist by design."""

import resource
from typing import Any

from proxmoxer import ProxmoxAPI

# Disable core dumps to protect API token in memory
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class ProxmoxClient:
    """Safe Proxmox API client — read-only and limited mutation only."""

    def __init__(self, host: str, user: str, token_name: str, token_value: str, verify_ssl: str | bool = True):
        self._api = ProxmoxAPI(
            host,
            user=user,
            token_name=token_name,
            token_value=token_value,
            verify_ssl=verify_ssl,
            port=8006,
        )

    # --- Read-only ---

    def list_nodes(self) -> list[dict]:
        return self._api.nodes.get()

    def node_status(self, node: str) -> dict:
        return self._api.nodes(node).status.get()

    def list_vms(self, node: str) -> list[dict]:
        return self._api.nodes(node).qemu.get()

    def list_containers(self, node: str) -> list[dict]:
        return self._api.nodes(node).lxc.get()

    def vm_status(self, node: str, vmid: int) -> dict:
        return self._api.nodes(node).qemu(vmid).status.current.get()

    def ct_status(self, node: str, vmid: int) -> dict:
        return self._api.nodes(node).lxc(vmid).status.current.get()

    def vm_config(self, node: str, vmid: int) -> dict:
        return self._api.nodes(node).qemu(vmid).config.get()

    def ct_config(self, node: str, vmid: int) -> dict:
        return self._api.nodes(node).lxc(vmid).config.get()

    def list_storage(self, node: str) -> list[dict]:
        return self._api.nodes(node).storage.get()

    def storage_content(self, node: str, storage: str) -> list[dict]:
        return self._api.nodes(node).storage(storage).content.get()

    def list_tasks(self, node: str) -> list[dict]:
        return self._api.nodes(node).tasks.get()

    def task_status(self, node: str, upid: str) -> dict:
        return self._api.nodes(node).tasks(upid).status.get()

    def list_snapshots(self, node: str, vmid: int, vm_type: str) -> list[dict]:
        if vm_type == "qemu":
            return self._api.nodes(node).qemu(vmid).snapshot.get()
        return self._api.nodes(node).lxc(vmid).snapshot.get()

    def cluster_resources(self, resource_type: str | None = None) -> list[dict]:
        params: dict[str, Any] = {}
        if resource_type:
            params["type"] = resource_type
        return self._api.cluster.resources.get(**params)

    def list_available_templates(self, node: str) -> list[dict]:
        return self._api.nodes(node).aplinfo.get()

    # --- Mutating (no delete operations) ---

    def create_vm(self, node: str, **kwargs: Any) -> str:
        return self._api.nodes(node).qemu.post(**kwargs)

    def clone_vm(self, node: str, vmid: int, **kwargs: Any) -> str:
        return self._api.nodes(node).qemu(vmid).clone.post(**kwargs)

    def create_container(self, node: str, **kwargs: Any) -> str:
        return self._api.nodes(node).lxc.post(**kwargs)

    def clone_container(self, node: str, vmid: int, **kwargs: Any) -> str:
        return self._api.nodes(node).lxc(vmid).clone.post(**kwargs)

    def start_vm(self, node: str, vmid: int) -> str:
        return self._api.nodes(node).qemu(vmid).status.start.post()

    def start_container(self, node: str, vmid: int) -> str:
        return self._api.nodes(node).lxc(vmid).status.start.post()

    def restart_vm(self, node: str, vmid: int) -> str:
        return self._api.nodes(node).qemu(vmid).status.reboot.post()

    def restart_container(self, node: str, vmid: int) -> str:
        return self._api.nodes(node).lxc(vmid).status.reboot.post()

    def resize_disk(self, node: str, vmid: int, vm_type: str, disk: str, size: str) -> Any:
        """Resize a disk. `size` must use '+' prefix (e.g., '+10G')."""
        if vm_type == "qemu":
            return self._api.nodes(node).qemu(vmid).resize.put(disk=disk, size=size)
        return self._api.nodes(node).lxc(vmid).resize.put(disk=disk, size=size)

    def update_config(self, node: str, vmid: int, vm_type: str, **kwargs: Any) -> Any:
        """Update VM/CT config (used for CPU/memory changes)."""
        if vm_type == "qemu":
            return self._api.nodes(node).qemu(vmid).config.put(**kwargs)
        return self._api.nodes(node).lxc(vmid).config.put(**kwargs)

    def restart_networking(self, node: str) -> str:
        return self._api.nodes(node).network.put()

    def download_template(self, node: str, storage: str, **kwargs: Any) -> str:
        return self._api.nodes(node).storage(storage)("download-url").post(**kwargs)

    # --- Guest agent execution ---

    def guest_exec(self, node: str, vmid: int, vm_type: str, command: str, args: list[str] | None = None) -> dict:
        """Execute a command inside a guest via QEMU Guest Agent."""
        params: dict[str, Any] = {"command": command}
        if args:
            # Proxmox API expects 'input-data' for stdin (optional) but not required.
            # Arguments are passed as a JSON array via the 'arg' key in newer versions,
            # or as individual arg0, arg1, ... in older versions.
            # proxmoxer handles the serialization.
            for i, arg in enumerate(args):
                params[f"arg{i}"] = arg

        if vm_type == "qemu":
            return self._api.nodes(node).qemu(vmid).agent.exec.post(**params)
        return self._api.nodes(node).lxc(vmid).agent.exec.post(**params)

    def guest_exec_status(self, node: str, vmid: int, vm_type: str, pid: int) -> dict:
        """Get the result of a previous guest exec call."""
        if vm_type == "qemu":
            return self._api.nodes(node).qemu(vmid).agent("exec-status").get(pid=pid)
        return self._api.nodes(node).lxc(vmid).agent("exec-status").get(pid=pid)
