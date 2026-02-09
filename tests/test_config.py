"""Tests for shared config module."""

import pytest

from servermonkey.config import validate_schema


class TestConfigSchema:
    def test_valid_config(self):
        config = {
            "proxmox": {
                "host": "test.example.com",
                "user": "test@pve",
                "token_name": "test",
                "ca_cert_path": "/tmp/test.pem",
            },
            "resource_caps": {
                "max_vcpus": 8,
                "max_memory_mb": 16384,
                "max_disk_grow_gb": 100,
            },
        }
        validate_schema(config)  # Should not raise

    def test_missing_proxmox_section(self):
        config = {
            "resource_caps": {"max_vcpus": 8, "max_memory_mb": 16384, "max_disk_grow_gb": 100},
        }
        with pytest.raises(ValueError, match="missing required section.*proxmox"):
            validate_schema(config)

    def test_missing_proxmox_key(self):
        config = {
            "proxmox": {"host": "test.example.com"},  # Missing user, token_name, ca_cert_path
            "resource_caps": {"max_vcpus": 8, "max_memory_mb": 16384, "max_disk_grow_gb": 100},
        }
        with pytest.raises(ValueError, match="missing required keys"):
            validate_schema(config)

    def test_resource_cap_not_integer(self):
        config = {
            "proxmox": {
                "host": "test.example.com",
                "user": "test@pve",
                "token_name": "test",
                "ca_cert_path": "/tmp/test.pem",
            },
            "resource_caps": {
                "max_vcpus": "eight",
                "max_memory_mb": 16384,
                "max_disk_grow_gb": 100,
            },
        }
        with pytest.raises(ValueError, match="must be an integer"):
            validate_schema(config)

    def test_resource_cap_not_positive(self):
        config = {
            "proxmox": {
                "host": "test.example.com",
                "user": "test@pve",
                "token_name": "test",
                "ca_cert_path": "/tmp/test.pem",
            },
            "resource_caps": {
                "max_vcpus": 0,
                "max_memory_mb": 16384,
                "max_disk_grow_gb": 100,
            },
        }
        with pytest.raises(ValueError, match="must be positive"):
            validate_schema(config)
