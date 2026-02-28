"""Shared fixtures for ServerMonkey tests."""

import pytest

from servermonkey import guardrails


@pytest.fixture(autouse=True)
def init_guardrails():
    """Initialize guardrails with a test config for every test."""
    guardrails.init({
        "proxmox": {
            "host": "test.example.com",
            "user": "test@pve",
            "token_name": "test",
            "ca_cert_path": "/tmp/test-ca.pem",
        },
        "resource_caps": {
            "max_vcpus": 8,
            "max_memory_mb": 16384,
            "max_disk_grow_gb": 100,
        },
        "protected": {
            "no_stop": [100, 101],
            "no_modify": [200],
        },
        "storage": {
            "allowed": ["local", "local-lvm"],
        },
        "scripts": {
            "apt-update": "apt update && apt upgrade -y",
            "check-dns": "resolvectl status",
        },
    })
    yield
    # Reset to None so tests that check uninitialized state work
    guardrails._config = None
