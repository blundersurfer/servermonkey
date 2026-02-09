"""Audit log format tests."""

import json
import os
import stat
from unittest.mock import patch

import pytest

from servermonkey import audit


@pytest.fixture
def audit_file(tmp_path):
    """Redirect audit log to a temp file."""
    audit_dir = tmp_path / "servermonkey"
    audit_file = audit_dir / "audit.jsonl"
    with patch.object(audit, "_AUDIT_DIR", audit_dir), \
         patch.object(audit, "_AUDIT_FILE", audit_file):
        yield audit_file


def test_log_tool_call_success(audit_file):
    audit.log_tool_call("list_nodes", {}, result=[{"node": "pve1"}])

    assert audit_file.exists()
    lines = audit_file.read_text().strip().split("\n")
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["tool"] == "list_nodes"
    assert entry["params"] == {}
    assert entry["result"] == [{"node": "pve1"}]
    assert "ts" in entry
    assert "epoch" in entry
    assert "error" not in entry


def test_log_tool_call_error(audit_file):
    audit.log_tool_call("create_vm", {"vmid": 999}, error="VMID out of range")

    lines = audit_file.read_text().strip().split("\n")
    entry = json.loads(lines[0])
    assert entry["tool"] == "create_vm"
    assert entry["error"] == "VMID out of range"
    assert "result" not in entry


def test_log_multiple_entries(audit_file):
    audit.log_tool_call("list_nodes", {}, result=[])
    audit.log_tool_call("node_status", {"node": "pve1"}, result={"status": "online"})

    lines = audit_file.read_text().strip().split("\n")
    assert len(lines) == 2


def test_result_truncation(audit_file):
    long_result = "x" * 2000
    audit.log_tool_call("test", {}, result=long_result)

    lines = audit_file.read_text().strip().split("\n")
    entry = json.loads(lines[0])
    assert entry["result"].endswith("...[truncated]")
    assert len(entry["result"]) < 1100


def test_large_list_summarized(audit_file):
    big_list = [{"id": i} for i in range(50)]
    audit.log_tool_call("test", {}, result=big_list)

    lines = audit_file.read_text().strip().split("\n")
    entry = json.loads(lines[0])
    assert entry["result"]["count"] == 50
    assert len(entry["result"]["first_5"]) == 5


def test_large_dict_summarized(audit_file):
    big_dict = {f"key_{i}": f"value_{i}" * 100 for i in range(50)}
    audit.log_tool_call("test", {}, result=big_dict)

    lines = audit_file.read_text().strip().split("\n")
    entry = json.loads(lines[0])
    assert entry["result"]["_truncated"] is True
    assert "_keys" in entry["result"]


def test_file_permissions(audit_file):
    audit.log_tool_call("test", {}, result="ok")

    mode = stat.S_IMODE(audit_file.stat().st_mode)
    assert mode == 0o600


def test_sensitive_param_redaction(audit_file):
    audit.log_tool_call("test", {"password": "secret123", "node": "pve1"}, result="ok")

    lines = audit_file.read_text().strip().split("\n")
    entry = json.loads(lines[0])
    assert entry["params"]["password"] == "[REDACTED]"
    assert entry["params"]["node"] == "pve1"


def test_directory_permissions(audit_file, tmp_path):
    audit.log_tool_call("test", {}, result="ok")
    audit_dir = tmp_path / "servermonkey"
    mode = stat.S_IMODE(audit_dir.stat().st_mode)
    assert mode == 0o700


def test_command_param_truncation(audit_file):
    long_command = "/usr/bin/very-long-" + "x" * 300
    audit.log_tool_call("guest_exec", {"command": long_command, "node": "pve1"}, result="ok")

    lines = audit_file.read_text().strip().split("\n")
    entry = json.loads(lines[0])
    assert entry["params"]["command"].endswith("...[truncated]")
    assert len(entry["params"]["command"]) < 250


def test_args_list_truncation(audit_file):
    big_args = [f"arg{i}" for i in range(100)]
    audit.log_tool_call("guest_exec", {"args": big_args, "node": "pve1"}, result="ok")

    lines = audit_file.read_text().strip().split("\n")
    entry = json.loads(lines[0])
    assert len(entry["params"]["args"]) == 5  # Truncated to first 5


def test_log_rotation(audit_file, tmp_path):
    """Log rotation should rename the file when over size limit."""
    # Write enough data to exceed the rotation limit
    with patch.object(audit, "_MAX_LOG_SIZE", 100):
        # Write first entry to create the file
        audit.log_tool_call("test", {}, result="x" * 200)
        # Second write should trigger rotation
        audit.log_tool_call("test2", {}, result="second")

    rotated = tmp_path / "servermonkey" / "audit.jsonl.1"
    assert rotated.exists()
    # Current file should have the new entry
    lines = audit_file.read_text().strip().split("\n")
    assert any("test2" in line for line in lines)
