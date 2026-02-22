"""Unit tests for all guardrails validation."""

from unittest.mock import patch

import pytest

from servermonkey import guardrails


class TestRequireInit:
    def test_uninitialized_raises(self):
        guardrails._config = None
        with pytest.raises(RuntimeError, match="guardrails.init"):
            guardrails.validate_storage("local")

    def test_initialized_works(self):
        guardrails.init({"storage": {"allowed": ["local"]}})
        guardrails.validate_storage("local")


class TestVmidValidation:
    def test_valid_vmid(self):
        guardrails.validate_vmid(100)
        guardrails.validate_vmid(999)
        guardrails.validate_vmid(999_999_999)

    def test_vmid_too_low(self):
        with pytest.raises(ValueError, match="VMID must be"):
            guardrails.validate_vmid(99)

    def test_vmid_too_high(self):
        with pytest.raises(ValueError, match="VMID must be"):
            guardrails.validate_vmid(1_000_000_000)

    def test_vmid_negative(self):
        with pytest.raises(ValueError, match="VMID must be"):
            guardrails.validate_vmid(-1)

    def test_vmid_bool_true_rejected(self):
        with pytest.raises(ValueError, match="VMID must be"):
            guardrails.validate_vmid(True)

    def test_vmid_bool_false_rejected(self):
        with pytest.raises(ValueError, match="VMID must be"):
            guardrails.validate_vmid(False)


class TestNodeValidation:
    def test_valid_node(self):
        guardrails.validate_node("pve1")
        guardrails.validate_node("eshu")
        guardrails.validate_node("node-01")

    def test_invalid_node_special_chars(self):
        with pytest.raises(ValueError, match="Invalid node name"):
            guardrails.validate_node("node;rm -rf /")

    def test_invalid_node_slash(self):
        with pytest.raises(ValueError, match="Invalid node name"):
            guardrails.validate_node("../etc/passwd")

    def test_invalid_node_empty(self):
        with pytest.raises(ValueError, match="Invalid node name"):
            guardrails.validate_node("")


class TestGuestNameValidation:
    def test_valid_names(self):
        guardrails.validate_guest_name("my-vm")
        guardrails.validate_guest_name("web01")
        guardrails.validate_guest_name("test.server")
        guardrails.validate_guest_name("a")

    def test_invalid_special_chars(self):
        with pytest.raises(ValueError, match="Invalid guest name"):
            guardrails.validate_guest_name("vm;drop table")

    def test_invalid_empty(self):
        with pytest.raises(ValueError, match="Invalid guest name"):
            guardrails.validate_guest_name("")


class TestStorageValidation:
    def test_valid_storage(self):
        guardrails.validate_storage("local")
        guardrails.validate_storage("local-lvm")

    def test_invalid_storage(self):
        with pytest.raises(ValueError, match="not in allowlist"):
            guardrails.validate_storage("nfs-backdoor")


class TestVmTypeValidation:
    def test_valid_types(self):
        guardrails.validate_vm_type("qemu")
        guardrails.validate_vm_type("lxc")

    def test_invalid_type(self):
        with pytest.raises(ValueError, match="vm_type must be"):
            guardrails.validate_vm_type("docker")


class TestResourceTypeValidation:
    def test_valid_types(self):
        guardrails.validate_resource_type("vm")
        guardrails.validate_resource_type("storage")
        guardrails.validate_resource_type("node")
        guardrails.validate_resource_type("sdn")

    def test_invalid_type(self):
        with pytest.raises(ValueError, match="resource_type must be"):
            guardrails.validate_resource_type("invalid")


class TestProtectedVms:
    def test_protected_stop(self):
        with pytest.raises(ValueError, match="protected and cannot be restarted"):
            guardrails.check_not_protected_stop(100)

    def test_unprotected_stop(self):
        guardrails.check_not_protected_stop(102)

    def test_protected_modify(self):
        with pytest.raises(ValueError, match="protected and cannot be modified"):
            guardrails.check_not_protected_modify(200)

    def test_unprotected_modify(self):
        guardrails.check_not_protected_modify(100)  # 100 is no_stop but not no_modify

    def test_protected_exec_no_stop(self):
        with pytest.raises(ValueError, match="protected and cannot have commands"):
            guardrails.check_not_protected_exec(100)

    def test_protected_exec_no_modify(self):
        with pytest.raises(ValueError, match="protected and cannot have commands"):
            guardrails.check_not_protected_exec(200)

    def test_unprotected_exec(self):
        guardrails.check_not_protected_exec(102)


class TestResourceCaps:
    def test_valid_cpu(self):
        guardrails.validate_cpu(1)
        guardrails.validate_cpu(8)

    def test_cpu_too_high(self):
        with pytest.raises(ValueError, match="CPU cores must be"):
            guardrails.validate_cpu(16)

    def test_cpu_zero(self):
        with pytest.raises(ValueError, match="CPU cores must be"):
            guardrails.validate_cpu(0)

    def test_valid_memory(self):
        guardrails.validate_memory(128)
        guardrails.validate_memory(16384)

    def test_memory_too_high(self):
        with pytest.raises(ValueError, match="Memory must be"):
            guardrails.validate_memory(32768)

    def test_memory_too_low(self):
        with pytest.raises(ValueError, match="Memory must be"):
            guardrails.validate_memory(64)

    def test_valid_disk_grow(self):
        guardrails.validate_disk_grow(1)
        guardrails.validate_disk_grow(100)

    def test_disk_grow_negative(self):
        with pytest.raises(ValueError, match="must be positive"):
            guardrails.validate_disk_grow(-10)

    def test_disk_grow_zero(self):
        with pytest.raises(ValueError, match="must be positive"):
            guardrails.validate_disk_grow(0)

    def test_disk_grow_too_large(self):
        with pytest.raises(ValueError, match="exceeds per-op cap"):
            guardrails.validate_disk_grow(200)


class TestDiskName:
    def test_valid_names(self):
        guardrails.validate_disk_name("scsi0")
        guardrails.validate_disk_name("virtio0")
        guardrails.validate_disk_name("ide2")
        guardrails.validate_disk_name("rootfs")
        guardrails.validate_disk_name("mp0")

    def test_invalid_name(self):
        with pytest.raises(ValueError, match="Invalid disk name"):
            guardrails.validate_disk_name("../../etc")

    def test_invalid_name_command(self):
        with pytest.raises(ValueError, match="Invalid disk name"):
            guardrails.validate_disk_name("$(rm -rf /)")

    def test_bare_disk_prefix_rejected(self):
        """Bare prefix without digit (e.g. 'scsi') should be rejected."""
        with pytest.raises(ValueError, match="Invalid disk name"):
            guardrails.validate_disk_name("scsi")
        with pytest.raises(ValueError, match="Invalid disk name"):
            guardrails.validate_disk_name("virtio")
        with pytest.raises(ValueError, match="Invalid disk name"):
            guardrails.validate_disk_name("mp")


class TestIncreaseOnly:
    def test_cpu_increase_ok(self):
        guardrails.validate_cpu_increase(2, 4)

    def test_cpu_decrease_blocked(self):
        with pytest.raises(ValueError, match="CPU reduction not allowed"):
            guardrails.validate_cpu_increase(4, 2)

    def test_memory_increase_ok(self):
        guardrails.validate_memory_increase(1024, 2048)

    def test_memory_decrease_blocked(self):
        with pytest.raises(ValueError, match="Memory reduction not allowed"):
            guardrails.validate_memory_increase(2048, 1024)


class TestScriptName:
    def test_valid_names(self):
        guardrails.validate_script_name("apt-update")
        guardrails.validate_script_name("bootstrap_ubuntu")
        guardrails.validate_script_name("check123")

    def test_invalid_path_traversal(self):
        with pytest.raises(ValueError, match="Invalid script name"):
            guardrails.validate_script_name("../../../etc/passwd")

    def test_invalid_command_injection(self):
        with pytest.raises(ValueError, match="Invalid script name"):
            guardrails.validate_script_name("test; rm -rf /")

    def test_invalid_spaces(self):
        with pytest.raises(ValueError, match="Invalid script name"):
            guardrails.validate_script_name("test script")


class TestTemplate:
    def test_valid_template(self):
        guardrails.validate_template("local:vztmpl/ubuntu-22.04-standard_22.04-1_amd64.tar.zst")

    def test_invalid_template(self):
        with pytest.raises(ValueError, match="Invalid template format"):
            guardrails.validate_template("")


class TestIsoValidation:
    def test_valid_iso(self):
        guardrails.validate_iso("local:iso/ubuntu-22.04-live-server-amd64.iso")

    def test_valid_img(self):
        guardrails.validate_iso("local:iso/virtio-win-0.1.iso")

    def test_invalid_iso(self):
        with pytest.raises(ValueError, match="Invalid ISO path"):
            guardrails.validate_iso("not-an-iso")

    def test_invalid_iso_command_injection(self):
        with pytest.raises(ValueError, match="Invalid ISO path"):
            guardrails.validate_iso("$(evil).iso")


class TestNetConfigValidation:
    def test_valid_net(self):
        guardrails.validate_net_config("virtio,bridge=vmbr0")
        guardrails.validate_net_config("name=eth0,bridge=vmbr0,ip=dhcp")

    def test_invalid_net_injection(self):
        with pytest.raises(ValueError, match="Invalid network config"):
            guardrails.validate_net_config("virtio;rm -rf /")


def _fake_getaddrinfo_public(host, port, **kwargs):
    """Return a public IP for any hostname."""
    return [(2, 1, 6, "", ("93.184.216.34", port or 443))]


def _fake_getaddrinfo_private(host, port, **kwargs):
    """Return a private IP (simulates DNS rebinding or internal hostname)."""
    return [(2, 1, 6, "", ("192.168.1.1", port or 443))]


def _fake_getaddrinfo_loopback(host, port, **kwargs):
    """Return loopback IP."""
    return [(2, 1, 6, "", ("127.0.0.1", port or 443))]


def _fake_getaddrinfo_ipv6_mapped(host, port, **kwargs):
    """Return IPv6-mapped private address."""
    return [(10, 1, 6, "", ("::ffff:192.168.1.1", port or 443, 0, 0))]


def _fake_getaddrinfo_link_local(host, port, **kwargs):
    """Return a link-local address."""
    return [(2, 1, 6, "", ("169.254.1.1", port or 443))]


class TestDownloadUrl:
    @patch("servermonkey.guardrails.socket.getaddrinfo", _fake_getaddrinfo_public)
    def test_valid_https(self):
        guardrails.validate_download_url("https://example.com/file.iso")

    def test_http_rejected(self):
        with pytest.raises(ValueError, match="must use HTTPS"):
            guardrails.validate_download_url("http://example.com/file.iso")

    def test_other_scheme_rejected(self):
        with pytest.raises(ValueError, match="must use HTTPS"):
            guardrails.validate_download_url("ftp://example.com/file.iso")

    @patch("servermonkey.guardrails.socket.getaddrinfo", _fake_getaddrinfo_private)
    def test_private_ip_rejected(self):
        with pytest.raises(ValueError, match="private/loopback"):
            guardrails.validate_download_url("https://192.168.1.1/file.iso")

    @patch("servermonkey.guardrails.socket.getaddrinfo", _fake_getaddrinfo_loopback)
    def test_loopback_rejected(self):
        with pytest.raises(ValueError, match="private/loopback"):
            guardrails.validate_download_url("https://127.0.0.1/file.iso")

    @patch("servermonkey.guardrails.socket.getaddrinfo", _fake_getaddrinfo_loopback)
    def test_localhost_rejected(self):
        with pytest.raises(ValueError, match="private/loopback"):
            guardrails.validate_download_url("https://localhost/file.iso")

    @patch("servermonkey.guardrails.socket.getaddrinfo", _fake_getaddrinfo_ipv6_mapped)
    def test_ipv6_mapped_private_rejected(self):
        """IPv6-mapped private addresses (::ffff:192.168.x.x) must be caught."""
        with pytest.raises(ValueError, match="private/loopback"):
            guardrails.validate_download_url("https://evil.example.com/file.iso")

    @patch("servermonkey.guardrails.socket.getaddrinfo", _fake_getaddrinfo_link_local)
    def test_link_local_rejected(self):
        with pytest.raises(ValueError, match="private/loopback"):
            guardrails.validate_download_url("https://metadata.example.com/file.iso")

    def test_no_hostname_rejected(self):
        with pytest.raises(ValueError, match="no hostname"):
            guardrails.validate_download_url("https:///file.iso")


class TestContentType:
    def test_valid_types(self):
        guardrails.validate_content_type("iso")
        guardrails.validate_content_type("vztmpl")

    def test_invalid_type(self):
        with pytest.raises(ValueError, match="content_type must be"):
            guardrails.validate_content_type("backup")


class TestUpid:
    def test_valid_upid(self):
        guardrails.validate_upid("UPID:pve1:000F4E1C:00B3E324:65A0F123:qmcreate:100:root@pam:")

    def test_invalid_upid(self):
        with pytest.raises(ValueError, match="Invalid UPID"):
            guardrails.validate_upid("not-a-upid")

    def test_upid_prefix_only_rejected(self):
        with pytest.raises(ValueError, match="Invalid UPID"):
            guardrails.validate_upid("UPID:arbitrary-junk")


class TestCommandPath:
    def test_valid_paths(self):
        guardrails.validate_command_path("/bin/echo")
        guardrails.validate_command_path("/usr/bin/apt")
        guardrails.validate_command_path("/usr/local/bin/my-tool")
        guardrails.validate_command_path("/bin/sh")

    def test_relative_path_rejected(self):
        with pytest.raises(ValueError, match="Invalid command path"):
            guardrails.validate_command_path("echo")

    def test_shell_metachar_rejected(self):
        with pytest.raises(ValueError, match="Invalid command path"):
            guardrails.validate_command_path("/bin/echo; rm -rf /")

    def test_backtick_rejected(self):
        with pytest.raises(ValueError, match="Invalid command path"):
            guardrails.validate_command_path("/bin/`whoami`")

    def test_subshell_rejected(self):
        with pytest.raises(ValueError, match="Invalid command path"):
            guardrails.validate_command_path("$(cat /etc/passwd)")

    def test_space_rejected(self):
        with pytest.raises(ValueError, match="Invalid command path"):
            guardrails.validate_command_path("/bin/my command")
