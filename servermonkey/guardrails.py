"""Validation, resource caps, and forbidden-operation enforcement."""

import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urlparse

# Loaded at init time from config.toml — None means not yet initialized
_config: dict[str, Any] | None = None


def init(config: dict[str, Any]) -> None:
    """Initialize guardrails with parsed config."""
    global _config
    _config = config


def _require_init() -> dict[str, Any]:
    """Return config or raise if guardrails were never initialized."""
    if _config is None:
        raise RuntimeError("guardrails.init() must be called before validation")
    return _config


# --- VMID validation ---

_VMID_MIN = 100
_VMID_MAX = 999_999_999


def validate_vmid(vmid: int) -> None:
    """Ensure VMID is in the valid Proxmox range."""
    if not isinstance(vmid, int) or vmid < _VMID_MIN or vmid > _VMID_MAX:
        raise ValueError(f"VMID must be an integer between {_VMID_MIN} and {_VMID_MAX}, got {vmid}")


# --- Node name validation ---

_NODE_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?$")


def validate_node(node: str) -> None:
    """Ensure node name is a valid hostname component."""
    if not _NODE_RE.match(node):
        raise ValueError(f"Invalid node name: {node!r}")


# --- Guest name validation (VM name / CT hostname) ---

_GUEST_NAME_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9._-]{0,61}[a-zA-Z0-9])?$")


def validate_guest_name(name: str) -> None:
    """Validate a VM name or container hostname."""
    if not _GUEST_NAME_RE.match(name):
        raise ValueError(
            f"Invalid guest name: {name!r}. "
            "Must start/end with alphanumeric, may contain hyphens, dots, underscores."
        )


# --- Storage allowlist ---


def validate_storage(storage: str) -> None:
    """Ensure storage is on the allowlist."""
    config = _require_init()
    allowed = config.get("storage", {}).get("allowed", [])
    if storage not in allowed:
        raise ValueError(f"Storage {storage!r} not in allowlist: {allowed}")


# --- VM type validation ---

_VALID_VM_TYPES = ("qemu", "lxc")


def validate_vm_type(vm_type: str) -> None:
    """Ensure vm_type is 'qemu' or 'lxc'."""
    if vm_type not in _VALID_VM_TYPES:
        raise ValueError(f"vm_type must be one of {_VALID_VM_TYPES}, got {vm_type!r}")


# --- Resource type validation ---

_VALID_RESOURCE_TYPES = ("vm", "storage", "node", "sdn")


def validate_resource_type(resource_type: str) -> None:
    """Validate the cluster resource type filter."""
    if resource_type not in _VALID_RESOURCE_TYPES:
        raise ValueError(f"resource_type must be one of {_VALID_RESOURCE_TYPES}, got {resource_type!r}")


# --- Protected VM checks ---


def check_not_protected_stop(vmid: int) -> None:
    """Raise if VMID is in the no-restart list."""
    config = _require_init()
    no_stop = config.get("protected", {}).get("no_stop", [])
    if vmid in no_stop:
        raise ValueError(f"VMID {vmid} is protected and cannot be restarted")


def check_not_protected_modify(vmid: int) -> None:
    """Raise if VMID is in the no-modify list."""
    config = _require_init()
    no_modify = config.get("protected", {}).get("no_modify", [])
    if vmid in no_modify:
        raise ValueError(f"VMID {vmid} is protected and cannot be modified")


def check_not_protected_exec(vmid: int) -> None:
    """Raise if VMID is in either the no-stop or no-modify list.

    Guest execution can both modify and stop a VM, so both lists apply.
    """
    config = _require_init()
    no_stop = config.get("protected", {}).get("no_stop", [])
    no_modify = config.get("protected", {}).get("no_modify", [])
    if vmid in no_stop or vmid in no_modify:
        raise ValueError(f"VMID {vmid} is protected and cannot have commands executed inside it")


# --- Resource caps ---


def validate_cpu(cores: int) -> None:
    """Enforce max vCPU cap."""
    config = _require_init()
    cap = config.get("resource_caps", {}).get("max_vcpus", 8)
    if cores < 1 or cores > cap:
        raise ValueError(f"CPU cores must be between 1 and {cap}, got {cores}")


def validate_memory(memory_mb: int) -> None:
    """Enforce max memory cap."""
    config = _require_init()
    cap = config.get("resource_caps", {}).get("max_memory_mb", 16384)
    if memory_mb < 128 or memory_mb > cap:
        raise ValueError(f"Memory must be between 128 MB and {cap} MB, got {memory_mb}")


def validate_disk_grow(size_increase_gb: int | float) -> None:
    """Enforce positive-only growth and per-op cap."""
    config = _require_init()
    if size_increase_gb <= 0:
        raise ValueError(f"Disk resize must be positive (grow only), got {size_increase_gb}")
    cap = config.get("resource_caps", {}).get("max_disk_grow_gb", 100)
    if size_increase_gb > cap:
        raise ValueError(f"Disk resize of {size_increase_gb} GB exceeds per-op cap of {cap} GB")


# --- Disk name validation ---

_DISK_RE = re.compile(r"^(scsi|virtio|ide|sata|efidisk|mp|rootfs)\d*$")


def validate_disk_name(disk: str) -> None:
    """Ensure disk name matches expected Proxmox patterns."""
    if not _DISK_RE.match(disk):
        raise ValueError(f"Invalid disk name: {disk!r}. Expected pattern like scsi0, virtio0, mp0, rootfs")


# --- CPU/memory increase-only enforcement ---


def validate_cpu_increase(current_cores: int, new_cores: int) -> None:
    """Ensure CPU change is an increase."""
    validate_cpu(new_cores)
    if new_cores < current_cores:
        raise ValueError(
            f"CPU reduction not allowed: current={current_cores}, requested={new_cores}. "
            "Only increases are permitted."
        )


def validate_memory_increase(current_mb: int, new_mb: int) -> None:
    """Ensure memory change is an increase."""
    validate_memory(new_mb)
    if new_mb < current_mb:
        raise ValueError(
            f"Memory reduction not allowed: current={current_mb} MB, requested={new_mb} MB. "
            "Only increases are permitted."
        )


# --- Script name validation ---

_SCRIPT_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def validate_script_name(script_name: str) -> None:
    """Ensure script name contains only safe characters."""
    if not _SCRIPT_NAME_RE.match(script_name):
        raise ValueError(
            f"Invalid script name: {script_name!r}. "
            "Only alphanumeric, hyphens, and underscores allowed."
        )


# --- Template format validation ---

_TEMPLATE_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\-+:/]+$")


def validate_template(template: str) -> None:
    """Validate ostemplate format."""
    if not _TEMPLATE_RE.match(template):
        raise ValueError(f"Invalid template format: {template!r}")


# --- ISO path validation ---

_ISO_PATH_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._\-+:/]+\.(iso|img)$")


def validate_iso(iso: str) -> None:
    """Validate ISO path format (storage:content/filename.iso)."""
    if not _ISO_PATH_RE.match(iso):
        raise ValueError(f"Invalid ISO path: {iso!r}. Expected format like 'local:iso/image.iso'")


# --- Network config validation ---

_NET_RE = re.compile(r"^[a-zA-Z0-9,=._\-/]+$")


def validate_net_config(net0: str) -> None:
    """Validate network configuration string (basic safety check)."""
    if not _NET_RE.match(net0):
        raise ValueError(f"Invalid network config: {net0!r}")


# --- URL validation for template downloads ---


def _is_private_ip(ip_str: str) -> bool:
    """Check if an IP address (v4 or v6) is private, loopback, link-local, or reserved."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved


def validate_download_url(url: str) -> None:
    """Validate download URL: must be HTTPS, resolved IPs must be public.

    Uses socket.getaddrinfo() to resolve the hostname and checks ALL returned
    addresses against ipaddress module to prevent SSRF via DNS rebinding,
    IPv6 mapped addresses, hex/octal IP encoding, etc.
    """
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"URL must use HTTPS, got scheme: {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError(f"URL has no hostname: {url!r}")
    hostname = parsed.hostname

    # Resolve hostname to actual IP addresses
    try:
        addrinfo = socket.getaddrinfo(hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {hostname!r}")

    if not addrinfo:
        raise ValueError(f"Hostname resolved to no addresses: {hostname!r}")

    for family, _type, _proto, _canonname, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        if _is_private_ip(ip_str):
            raise ValueError(
                f"URL hostname resolves to private/loopback address: "
                f"{hostname!r} -> {ip_str}"
            )


# --- Content type validation ---

_VALID_CONTENT_TYPES = ("iso", "vztmpl")


def validate_content_type(content_type: str) -> None:
    """Ensure content type is iso or vztmpl."""
    if content_type not in _VALID_CONTENT_TYPES:
        raise ValueError(f"content_type must be one of {_VALID_CONTENT_TYPES}, got {content_type!r}")


# --- Command path validation (for guest_exec) ---

_COMMAND_PATH_RE = re.compile(r"^/[a-zA-Z0-9/_.\-]+$")


def validate_command_path(command: str) -> None:
    """Ensure command is an absolute path with safe characters.

    Prevents shell metacharacter injection via the command parameter.
    Commands must be absolute paths (e.g., /bin/echo, /usr/bin/apt).
    """
    if not _COMMAND_PATH_RE.match(command):
        raise ValueError(
            f"Invalid command path: {command!r}. "
            "Must be an absolute path (e.g., /bin/echo, /usr/local/bin/my-tool)."
        )


# --- UPID validation ---

_UPID_RE = re.compile(
    r"^UPID:[a-zA-Z0-9\-]+:[0-9A-Fa-f]+:[0-9A-Fa-f]+:"
    r"[0-9A-Fa-f]+:[a-zA-Z]+:[0-9]*:[a-zA-Z0-9@.\-]+:$"
)


def validate_upid(upid: str) -> None:
    """Validate UPID format (Proxmox task identifier)."""
    if not _UPID_RE.match(upid):
        raise ValueError(f"Invalid UPID format: {upid!r}")
