"""FastMCP server with all tool definitions for ServerMonkey."""

import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

from servermonkey import audit, guardrails
from servermonkey.client import ProxmoxClient
from servermonkey.config import find_scripts_dir, load_config
from servermonkey.credentials import ensure_ca_cert, get_api_token


# --- Server initialization ---

mcp = FastMCP("ServerMonkey", instructions="Secure Proxmox MCP server. Use list_nodes to start.")

_client: ProxmoxClient | None = None
_config: dict[str, Any] | None = None
_scripts_dir: Path | None = None


def _get_client() -> ProxmoxClient:
    global _client, _config, _scripts_dir
    if _client is None:
        _config = load_config()
        _scripts_dir = find_scripts_dir()
        guardrails.init(_config)

        px = _config["proxmox"]
        token = get_api_token(px["host"])
        ca_path = ensure_ca_cert(px["ca_cert_path"])

        _client = ProxmoxClient(
            host=px["host"],
            user=px["user"],
            token_name=px["token_name"],
            token_value=token,
            verify_ssl=ca_path,
        )
    return _client


def _get_config() -> dict[str, Any]:
    if _config is None:
        _get_client()
    if _config is None:
        raise RuntimeError("Config not loaded after client initialization")
    return _config


def _get_scripts_dir() -> Path:
    if _scripts_dir is None:
        _get_client()
    if _scripts_dir is None:
        raise RuntimeError("Scripts directory not resolved after client initialization")
    return _scripts_dir


@mcp.tool()
def reconnect() -> str:
    """Reset the Proxmox connection. Use after running servermonkey-setup or editing config.toml."""
    global _client, _config, _scripts_dir
    _client = None
    _config = None
    _scripts_dir = None
    result = "Connection reset. Next tool call will reconnect with fresh config."
    audit.log_tool_call("reconnect", {}, result=result)
    return result


# --- Helper to wrap tool calls with audit logging ---


def _audited(tool_name: str, params: dict[str, Any], fn):
    """Execute fn(), audit-log the call, and return the result."""
    try:
        result = fn()
        audit.log_tool_call(tool_name, params, result=result)
        return result
    except Exception as e:
        audit.log_tool_call(tool_name, params, error=str(e))
        raise


# --- Helper for guest exec polling ---

_EXEC_POLL_TIMEOUT = 30
_EXEC_POLL_INITIAL_DELAY = 0.25
_EXEC_POLL_MAX_DELAY = 2.0


def _wait_for_exec(client: ProxmoxClient, node: str, vmid: int, vm_type: str, pid: int) -> dict:
    """Poll guest exec status with exponential backoff until completion or timeout."""
    deadline = time.time() + _EXEC_POLL_TIMEOUT
    delay = _EXEC_POLL_INITIAL_DELAY
    while time.time() < deadline:
        time.sleep(delay)
        status = client.guest_exec_status(node, vmid, vm_type, pid)
        if status.get("exited"):
            return status
        delay = min(delay * 2, _EXEC_POLL_MAX_DELAY)
    return {"error": f"Guest exec pid={pid} did not complete within {_EXEC_POLL_TIMEOUT}s", "pid": pid}


# ============================================================
# READ-ONLY TOOLS (15)
# ============================================================


@mcp.tool()
def list_nodes() -> list[dict]:
    """List all nodes in the Proxmox cluster."""
    client = _get_client()
    return _audited("list_nodes", {}, lambda: client.list_nodes())


@mcp.tool()
def node_status(node: str) -> dict:
    """Get detailed status of a specific node (CPU, memory, uptime)."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        return client.node_status(node)
    return _audited("node_status", {"node": node}, _call)


@mcp.tool()
def list_vms(node: str) -> list[dict]:
    """List all QEMU VMs on a node."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        return client.list_vms(node)
    return _audited("list_vms", {"node": node}, _call)


@mcp.tool()
def list_containers(node: str) -> list[dict]:
    """List all LXC containers on a node."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        return client.list_containers(node)
    return _audited("list_containers", {"node": node}, _call)


@mcp.tool()
def vm_status(node: str, vmid: int) -> dict:
    """Get current status of a QEMU VM."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        return client.vm_status(node, vmid)
    return _audited("vm_status", {"node": node, "vmid": vmid}, _call)


@mcp.tool()
def ct_status(node: str, vmid: int) -> dict:
    """Get current status of an LXC container."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        return client.ct_status(node, vmid)
    return _audited("ct_status", {"node": node, "vmid": vmid}, _call)


@mcp.tool()
def vm_config(node: str, vmid: int) -> dict:
    """Get configuration of a QEMU VM."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        return client.vm_config(node, vmid)
    return _audited("vm_config", {"node": node, "vmid": vmid}, _call)


@mcp.tool()
def ct_config(node: str, vmid: int) -> dict:
    """Get configuration of an LXC container."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        return client.ct_config(node, vmid)
    return _audited("ct_config", {"node": node, "vmid": vmid}, _call)


@mcp.tool()
def ct_interfaces(node: str, vmid: int) -> list[dict]:
    """Get network interfaces and IP addresses of a running LXC container."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        return client.ct_interfaces(node, vmid)
    return _audited("ct_interfaces", {"node": node, "vmid": vmid}, _call)


@mcp.tool()
def list_storage(node: str) -> list[dict]:
    """List all storage pools on a node."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        return client.list_storage(node)
    return _audited("list_storage", {"node": node}, _call)


@mcp.tool()
def storage_content(node: str, storage: str) -> list[dict]:
    """List contents of a storage pool (ISOs, templates, disk images)."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_storage(storage)
        return client.storage_content(node, storage)
    return _audited("storage_content", {"node": node, "storage": storage}, _call)


@mcp.tool()
def list_tasks(node: str) -> list[dict]:
    """List recent tasks on a node."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        return client.list_tasks(node)
    return _audited("list_tasks", {"node": node}, _call)


@mcp.tool()
def task_status(node: str, upid: str) -> dict:
    """Get status of a specific task by UPID."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_upid(upid)
        return client.task_status(node, upid)
    return _audited("task_status", {"node": node, "upid": upid}, _call)


@mcp.tool()
def list_snapshots(node: str, vmid: int, vm_type: str) -> list[dict]:
    """List snapshots of a VM or container. vm_type: 'qemu' or 'lxc'."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        guardrails.validate_vm_type(vm_type)
        return client.list_snapshots(node, vmid, vm_type)
    return _audited(
        "list_snapshots",
        {"node": node, "vmid": vmid, "vm_type": vm_type},
        _call,
    )


@mcp.tool()
def cluster_resources(resource_type: str | None = None) -> list[dict]:
    """List cluster resources. Optional filter: 'vm', 'storage', 'node', 'sdn'."""
    client = _get_client()
    def _call():
        if resource_type is not None:
            guardrails.validate_resource_type(resource_type)
        return client.cluster_resources(resource_type)
    return _audited(
        "cluster_resources",
        {"resource_type": resource_type},
        _call,
    )


@mcp.tool()
def list_available_templates(node: str) -> list[dict]:
    """List available appliance templates that can be downloaded."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        return client.list_available_templates(node)
    return _audited("list_available_templates", {"node": node}, _call)


# ============================================================
# MUTATING TOOLS (10)
# ============================================================


@mcp.tool()
def create_vm(
    node: str,
    vmid: int,
    name: str,
    memory: int,
    cores: int,
    storage: str,
    iso: str,
    net0: str = "virtio,bridge=vmbr0",
) -> str:
    """Create a new QEMU VM."""
    client = _get_client()
    params = {
        "node": node, "vmid": vmid, "name": name,
        "memory": memory, "cores": cores, "storage": storage,
        "iso": iso, "net0": net0,
    }
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        guardrails.validate_guest_name(name)
        guardrails.validate_cpu(cores)
        guardrails.validate_memory(memory)
        guardrails.validate_storage(storage)
        guardrails.validate_iso(iso)
        guardrails.validate_net_config(net0)
        return client.create_vm(
            node, vmid=vmid, name=name, memory=memory, cores=cores,
            storage=storage, ide2=f"{iso},media=cdrom", net0=net0,
        )
    return _audited("create_vm", params, _call)


@mcp.tool()
def clone_vm(
    node: str,
    vmid: int,
    newid: int,
    name: str = "",
    full: bool = True,
    storage: str = "",
) -> str:
    """Clone an existing QEMU VM."""
    client = _get_client()
    params = {"node": node, "vmid": vmid, "newid": newid, "name": name, "full": full, "storage": storage}
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        guardrails.validate_vmid(newid)
        if name:
            guardrails.validate_guest_name(name)
        if storage:
            guardrails.validate_storage(storage)
        kwargs: dict[str, Any] = {"newid": newid, "full": int(full)}
        if name:
            kwargs["name"] = name
        if storage:
            kwargs["storage"] = storage
        return client.clone_vm(node, vmid, **kwargs)
    return _audited("clone_vm", params, _call)


@mcp.tool()
def create_container(
    node: str,
    vmid: int,
    hostname: str,
    ostemplate: str,
    memory: int = 512,
    cores: int = 1,
    storage: str = "local-lvm",
    net0: str = "name=eth0,bridge=vmbr0,ip=dhcp",
    ssh_public_keys: str = "",
) -> str:
    """Create a new LXC container."""
    client = _get_client()
    params = {
        "node": node, "vmid": vmid, "hostname": hostname,
        "ostemplate": ostemplate, "memory": memory, "cores": cores,
        "storage": storage, "net0": net0,
    }
    if ssh_public_keys:
        params["ssh_public_keys"] = ssh_public_keys
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        guardrails.validate_guest_name(hostname)
        guardrails.validate_template(ostemplate)
        guardrails.validate_cpu(cores)
        guardrails.validate_memory(memory)
        guardrails.validate_storage(storage)
        guardrails.validate_net_config(net0)
        if ssh_public_keys:
            guardrails.validate_ssh_public_keys(ssh_public_keys)
        create_kwargs = dict(
            vmid=vmid, hostname=hostname, ostemplate=ostemplate,
            memory=memory, cores=cores, storage=storage, net0=net0,
        )
        if ssh_public_keys:
            create_kwargs["ssh-public-keys"] = ssh_public_keys
        return client.create_container(node, **create_kwargs)
    return _audited("create_container", params, _call)


@mcp.tool()
def clone_container(
    node: str,
    vmid: int,
    newid: int,
    hostname: str = "",
    full: bool = True,
    storage: str = "",
) -> str:
    """Clone an existing LXC container."""
    client = _get_client()
    params = {"node": node, "vmid": vmid, "newid": newid, "hostname": hostname, "full": full, "storage": storage}
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        guardrails.validate_vmid(newid)
        if hostname:
            guardrails.validate_guest_name(hostname)
        if storage:
            guardrails.validate_storage(storage)
        kwargs: dict[str, Any] = {"newid": newid, "full": int(full)}
        if hostname:
            kwargs["hostname"] = hostname
        if storage:
            kwargs["storage"] = storage
        return client.clone_container(node, vmid, **kwargs)
    return _audited("clone_container", params, _call)


@mcp.tool()
def start_guest(node: str, vmid: int, vm_type: str) -> str:
    """Start a VM or container. vm_type: 'qemu' or 'lxc'. Protected VMs (no_stop) cannot be started."""
    client = _get_client()
    params = {"node": node, "vmid": vmid, "vm_type": vm_type}
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        guardrails.validate_vm_type(vm_type)
        guardrails.check_not_protected_stop(vmid)
        if vm_type == "qemu":
            return client.start_vm(node, vmid)
        return client.start_container(node, vmid)
    return _audited("start_guest", params, _call)


@mcp.tool()
def restart_guest(node: str, vmid: int, vm_type: str) -> str:
    """Restart a VM or container. vm_type: 'qemu' or 'lxc'. Protected VMs cannot be restarted."""
    client = _get_client()
    params = {"node": node, "vmid": vmid, "vm_type": vm_type}
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        guardrails.validate_vm_type(vm_type)
        guardrails.check_not_protected_stop(vmid)
        if vm_type == "qemu":
            return client.restart_vm(node, vmid)
        return client.restart_container(node, vmid)
    return _audited("restart_guest", params, _call)


@mcp.tool()
def resize_disk(node: str, vmid: int, vm_type: str, disk: str, size_increase_gb: int) -> Any:
    """Resize (grow) a disk. Only positive increases allowed. vm_type: 'qemu' or 'lxc'."""
    client = _get_client()
    params = {"node": node, "vmid": vmid, "vm_type": vm_type, "disk": disk, "size_increase_gb": size_increase_gb}
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        guardrails.validate_vm_type(vm_type)
        guardrails.validate_disk_name(disk)
        guardrails.validate_disk_grow(size_increase_gb)
        guardrails.check_not_protected_modify(vmid)
        size = f"+{size_increase_gb}G"
        return client.resize_disk(node, vmid, vm_type, disk, size)
    return _audited("resize_disk", params, _call)


@mcp.tool()
def update_cpu_memory(
    node: str,
    vmid: int,
    vm_type: str,
    cores: int | None = None,
    memory_mb: int | None = None,
) -> Any:
    """Update CPU cores and/or memory for a VM/CT. Only increases allowed. vm_type: 'qemu' or 'lxc'."""
    client = _get_client()
    params = {"node": node, "vmid": vmid, "vm_type": vm_type, "cores": cores, "memory_mb": memory_mb}
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        guardrails.validate_vm_type(vm_type)
        guardrails.check_not_protected_modify(vmid)

        if cores is None and memory_mb is None:
            raise ValueError("Must specify at least one of: cores, memory_mb")

        # Fetch current config to enforce increase-only
        if vm_type == "qemu":
            current = client.vm_config(node, vmid)
        else:
            current = client.ct_config(node, vmid)

        update_kwargs: dict[str, Any] = {}
        if cores is not None:
            current_cores = current.get("cores", 1)
            guardrails.validate_cpu_increase(current_cores, cores)
            update_kwargs["cores"] = cores
        if memory_mb is not None:
            current_memory = current.get("memory", 512)
            guardrails.validate_memory_increase(current_memory, memory_mb)
            update_kwargs["memory"] = memory_mb

        return client.update_config(node, vmid, vm_type, **update_kwargs)
    return _audited("update_cpu_memory", params, _call)


@mcp.tool()
def restart_networking(node: str) -> str:
    """Apply pending network configuration changes on a node."""
    client = _get_client()
    def _call():
        guardrails.validate_node(node)
        return client.restart_networking(node)
    return _audited("restart_networking", {"node": node}, _call)


@mcp.tool()
def download_template(
    node: str,
    storage: str,
    content_type: str,
    url: str = "",
    template: str = "",
) -> str:
    """Download a template or ISO to storage. content_type: 'iso' or 'vztmpl'.

    IMPORTANT: This tool instructs the Proxmox server to fetch from the provided URL.
    Each invocation should be reviewed by the user to verify the download source.
    Only HTTPS URLs are allowed; private/loopback IPs are blocked.
    """
    client = _get_client()
    params = {"node": node, "storage": storage, "content_type": content_type, "url": url, "template": template}
    def _call():
        guardrails.validate_node(node)
        guardrails.validate_storage(storage)
        guardrails.validate_content_type(content_type)
        if url:
            guardrails.validate_download_url(url)

        kwargs: dict[str, Any] = {"content": content_type}
        if url:
            kwargs["url"] = url
            # Extract filename from URL path only (strip query string, fragment)
            url_path = urlparse(url).path
            filename = Path(url_path).name
            if not filename or "/" in filename or "\\" in filename:
                raise ValueError(f"Cannot extract safe filename from URL: {url!r}")
            kwargs["filename"] = filename
        elif template:
            kwargs["template"] = template
        else:
            raise ValueError("Must specify either 'url' or 'template'")

        return client.download_template(node, storage, **kwargs)
    return _audited("download_template", params, _call)


# ============================================================
# GUEST EXECUTION TOOLS (2)
# ============================================================


def _resolve_script(script_name: str) -> str:
    """Look up a script by name — inline from config or .sh file."""
    guardrails.validate_script_name(script_name)
    config = _get_config()
    scripts_dir = _get_scripts_dir()

    # Check inline scripts in config
    inline = config.get("scripts", {}).get(script_name)
    if inline:
        return inline

    # Check scripts/ directory
    script_file = scripts_dir / f"{script_name}.sh"
    if script_file.is_file():
        return script_file.read_text()

    # Check scripts/apps/*/ subdirectories
    apps_dir = scripts_dir / "apps"
    if apps_dir.is_dir():
        for app_script in apps_dir.glob(f"*/{script_name}.sh"):
            if app_script.is_file():
                return app_script.read_text()

    available_inline = list(config.get("scripts", {}).keys())
    available_files = [f.stem for f in scripts_dir.glob("*.sh")] if scripts_dir.is_dir() else []
    if apps_dir.is_dir():
        available_files += [f.stem for f in apps_dir.glob("*/*.sh")]
    raise ValueError(
        f"Script {script_name!r} not found. "
        f"Available inline: {available_inline}, files: {available_files}"
    )


@mcp.tool()
def run_script(node: str, vmid: int, vm_type: str, script_name: str, args: list[str] | None = None) -> dict:
    """Run a pre-approved script inside a guest VM/CT via QEMU Guest Agent.

    Scripts are defined in config.toml [scripts] table (inline one-liners)
    or as .sh files in the scripts/ directory. Only pre-vetted scripts can run.
    """
    client = _get_client()

    params = {"node": node, "vmid": vmid, "vm_type": vm_type, "script_name": script_name, "args": args}

    def _exec():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        guardrails.validate_vm_type(vm_type)
        guardrails.check_not_protected_exec(vmid)

        script_body = _resolve_script(script_name)

        # Use shell positional parameters to safely pass args without injection.
        # "$@" expands each positional parameter as a separate word, preventing
        # shell interpretation of user-supplied values.
        # Ensure script_body ends with a newline before appending "$@"
        if args:
            body = script_body if script_body.endswith("\n") else script_body + "\n"
            exec_args = ["-c", body + '"$@"', "sh"] + args
        else:
            exec_args = ["-c", script_body]

        result = client.guest_exec(node, vmid, vm_type, "/bin/sh", exec_args)
        pid = result.get("pid")
        if pid is not None:
            return _wait_for_exec(client, node, vmid, vm_type, pid)
        return result

    return _audited("run_script", params, _exec)


@mcp.tool()
def guest_exec(node: str, vmid: int, vm_type: str, command: str, args: list[str] | None = None) -> dict:
    """Execute an arbitrary command inside a guest VM/CT via QEMU Guest Agent.

    IMPORTANT: This tool requires human approval for each invocation.
    Claude Code's permission system ensures the user sees the exact command
    before it runs. Protected VMs cannot be targeted.
    """
    client = _get_client()

    params = {"node": node, "vmid": vmid, "vm_type": vm_type, "command": command, "args": args}

    def _exec():
        guardrails.validate_node(node)
        guardrails.validate_vmid(vmid)
        guardrails.validate_vm_type(vm_type)
        guardrails.check_not_protected_exec(vmid)
        guardrails.validate_command_path(command)

        result = client.guest_exec(node, vmid, vm_type, command, args)
        pid = result.get("pid")
        if pid is not None:
            return _wait_for_exec(client, node, vmid, vm_type, pid)
        return result

    return _audited("guest_exec", params, _exec)


# --- Entry point ---

def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
