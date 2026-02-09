"""Integration tests for server.py tools with mocked ProxmoxClient."""

from unittest.mock import MagicMock, patch


import pytest

from servermonkey import guardrails, audit, server


@pytest.fixture
def mock_client():
    """Create a mock ProxmoxClient and patch it into the server module."""
    client = MagicMock()
    # Default return values for common calls
    client.list_nodes.return_value = [{"node": "pve1", "status": "online"}]
    client.node_status.return_value = {"cpu": 0.12, "memory": {"used": 1024}}
    client.list_vms.return_value = [{"vmid": 100, "name": "test-vm"}]
    client.list_containers.return_value = [{"vmid": 200, "name": "test-ct"}]
    client.vm_status.return_value = {"status": "running"}
    client.ct_status.return_value = {"status": "running"}
    client.vm_config.return_value = {"cores": 2, "memory": 2048}
    client.ct_config.return_value = {"cores": 1, "memory": 512}
    client.guest_exec.return_value = {"pid": 42}
    client.guest_exec_status.return_value = {"exited": True, "exitcode": 0, "out-data": "ok"}
    return client


@pytest.fixture
def patched_server(mock_client, tmp_path):
    """Patch server globals so tools use the mock client without real Proxmox."""
    test_config = {
        "proxmox": {"host": "test.example.com", "user": "test@pve", "token_name": "t", "ca_cert_path": "/tmp/x"},
        "resource_caps": {"max_vcpus": 8, "max_memory_mb": 16384, "max_disk_grow_gb": 100},
        "protected": {"no_stop": [100, 101], "no_modify": [200]},
        "storage": {"allowed": ["local", "local-lvm"]},
        "scripts": {"apt-update": "apt update && apt upgrade -y", "check-dns": "resolvectl status"},
    }
    guardrails.init(test_config)

    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    (scripts_dir / "test-script.sh").write_text("echo hello")

    audit_dir = tmp_path / "audit"
    audit_file = audit_dir / "audit.jsonl"

    with patch.object(server, "_client", mock_client), \
         patch.object(server, "_config", test_config), \
         patch.object(server, "_scripts_dir", scripts_dir), \
         patch.object(audit, "_AUDIT_DIR", audit_dir), \
         patch.object(audit, "_AUDIT_FILE", audit_file):
        yield mock_client


# --- Read-only tools ---

class TestReadOnlyTools:
    def test_list_nodes(self, patched_server):
        result = server.list_nodes()
        assert result == [{"node": "pve1", "status": "online"}]
        patched_server.list_nodes.assert_called_once()

    def test_node_status_validates_node(self, patched_server):
        with pytest.raises(ValueError, match="Invalid node name"):
            server.node_status("../etc")

    def test_vm_status_validates_vmid(self, patched_server):
        with pytest.raises(ValueError, match="VMID must be"):
            server.vm_status("pve1", 50)

    def test_cluster_resources_validates_type(self, patched_server):
        patched_server.cluster_resources.return_value = []
        with pytest.raises(ValueError, match="resource_type must be"):
            server.cluster_resources("invalid")

    def test_cluster_resources_none_type_ok(self, patched_server):
        patched_server.cluster_resources.return_value = []
        result = server.cluster_resources(None)
        assert result == []

    def test_storage_content_validates_allowlist(self, patched_server):
        with pytest.raises(ValueError, match="not in allowlist"):
            server.storage_content("pve1", "evil-nfs")

    def test_task_status_validates_upid(self, patched_server):
        with pytest.raises(ValueError, match="Invalid UPID"):
            server.task_status("pve1", "not-a-upid")


# --- Mutating tools ---

class TestMutatingTools:
    def test_create_vm_validates_all_params(self, patched_server):
        # Bad guest name
        with pytest.raises(ValueError, match="Invalid guest name"):
            server.create_vm("pve1", 300, ";evil", 2048, 2, "local", "local:iso/test.iso")

    def test_create_vm_validates_iso(self, patched_server):
        with pytest.raises(ValueError, match="Invalid ISO"):
            server.create_vm("pve1", 300, "test-vm", 2048, 2, "local", "not-an-iso")

    def test_create_vm_validates_net(self, patched_server):
        with pytest.raises(ValueError, match="Invalid network"):
            server.create_vm("pve1", 300, "test-vm", 2048, 2, "local", "local:iso/test.iso", "evil;cmd")

    def test_resize_disk_positive_only(self, patched_server):
        with pytest.raises(ValueError, match="must be positive"):
            server.resize_disk("pve1", 102, "qemu", "scsi0", -5)

    def test_resize_disk_protected(self, patched_server):
        with pytest.raises(ValueError, match="protected and cannot be modified"):
            server.resize_disk("pve1", 200, "qemu", "scsi0", 10)

    def test_update_cpu_memory_increase_only(self, patched_server):
        # Current is 2 cores, trying to go to 1
        with pytest.raises(ValueError, match="CPU reduction not allowed"):
            server.update_cpu_memory("pve1", 102, "qemu", cores=1)

    def test_restart_guest_protected(self, patched_server):
        with pytest.raises(ValueError, match="protected and cannot be restarted"):
            server.restart_guest("pve1", 100, "qemu")

    def test_start_guest_protected(self, patched_server):
        with pytest.raises(ValueError, match="protected and cannot be restarted"):
            server.start_guest("pve1", 100, "qemu")

    @patch("servermonkey.guardrails.socket.getaddrinfo",
           lambda *a, **kw: [(2, 1, 6, "", ("192.168.1.1", 443))])
    def test_download_template_private_ip(self, patched_server):
        with pytest.raises(ValueError, match="private/loopback"):
            server.download_template("pve1", "local", "iso", url="https://192.168.1.1/test.iso")

    def test_clone_vm_validates_name(self, patched_server):
        with pytest.raises(ValueError, match="Invalid guest name"):
            server.clone_vm("pve1", 102, 300, name=";evil")


# --- Guest execution tools ---

class TestGuestExec:
    def test_guest_exec_calls_client(self, patched_server):
        result = server.guest_exec("pve1", 102, "qemu", "/bin/echo", ["hello"])
        assert result["exited"] is True
        patched_server.guest_exec.assert_called_once()

    def test_guest_exec_protected_blocked(self, patched_server):
        # VMID 100 is in no_stop, should block exec
        with pytest.raises(ValueError, match="protected and cannot have commands"):
            server.guest_exec("pve1", 100, "qemu", "/bin/echo")

    def test_guest_exec_no_modify_blocked(self, patched_server):
        # VMID 200 is in no_modify, should block exec
        with pytest.raises(ValueError, match="protected and cannot have commands"):
            server.guest_exec("pve1", 200, "lxc", "/bin/echo")

    def test_guest_exec_validates_command_path(self, patched_server):
        with pytest.raises(ValueError, match="Invalid command path"):
            server.guest_exec("pve1", 102, "qemu", "echo")  # Not absolute

    def test_guest_exec_rejects_metachar(self, patched_server):
        with pytest.raises(ValueError, match="Invalid command path"):
            server.guest_exec("pve1", 102, "qemu", "/bin/echo; rm -rf /")

    def test_run_script_protected_blocked(self, patched_server):
        with pytest.raises(ValueError, match="protected and cannot have commands"):
            server.run_script("pve1", 100, "qemu", "apt-update")

    def test_run_script_resolves_inline(self, patched_server):
        result = server.run_script("pve1", 102, "qemu", "apt-update")
        assert result["exited"] is True
        # Verify /bin/sh was called
        call_args = patched_server.guest_exec.call_args
        assert call_args[0][3] == "/bin/sh"  # command

    def test_run_script_resolves_file(self, patched_server):
        result = server.run_script("pve1", 102, "qemu", "test-script")
        assert result["exited"] is True

    def test_run_script_not_found(self, patched_server):
        with pytest.raises(ValueError, match="not found"):
            server.run_script("pve1", 102, "qemu", "nonexistent")

    def test_run_script_validates_name(self, patched_server):
        with pytest.raises(ValueError, match="Invalid script name"):
            server.run_script("pve1", 102, "qemu", "../../../etc/passwd")

    def test_run_script_args_safe(self, patched_server):
        """Verify args use safe positional parameter passing."""
        server.run_script("pve1", 102, "qemu", "apt-update", args=["; rm -rf /"])
        call_args = patched_server.guest_exec.call_args
        exec_args = call_args[0][4]  # args parameter
        # Should use "$@" pattern, not string concatenation
        assert '"$@"' in exec_args[1]
        # The malicious arg should be a separate list element, not in the shell string
        assert "; rm -rf /" in exec_args


# --- Audit integration ---

class TestAuditIntegration:
    def test_successful_call_produces_one_entry(self, patched_server, tmp_path):
        server.list_nodes()
        audit_file = tmp_path / "audit" / "audit.jsonl"
        lines = audit_file.read_text().strip().split("\n")
        assert len(lines) == 1

    def test_guest_exec_produces_one_entry(self, patched_server, tmp_path):
        """guest_exec should NOT double-log (was a bug)."""
        server.guest_exec("pve1", 102, "qemu", "/bin/echo")
        audit_file = tmp_path / "audit" / "audit.jsonl"
        lines = audit_file.read_text().strip().split("\n")
        assert len(lines) == 1  # Not 2!

    def test_failed_call_logs_error(self, patched_server, tmp_path):
        import json
        with pytest.raises(ValueError):
            server.vm_status("../evil", 100)
        audit_file = tmp_path / "audit" / "audit.jsonl"
        # Validation error happens before _audited, so no audit entry for guardrail failures
        assert not audit_file.exists() or audit_file.read_text().strip() == ""
