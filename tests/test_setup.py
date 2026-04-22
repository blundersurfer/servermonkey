"""Tests for interactive setup module."""

from pathlib import Path
from unittest.mock import patch

import pytest

from servermonkey.setup import _update_config_key, setup_credentials

SAMPLE_CONFIG = """\
[proxmox]
host = "test.example.com"
user = "old@pam"
token_name = "old-token"
ca_cert_path = "/tmp/test-ca.pem"

[resource_caps]
max_vcpus = 8
"""


class TestUpdateConfigKey:
    def test_replaces_value(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(SAMPLE_CONFIG)

        _update_config_key(config_file, "user", "new@pve")

        text = config_file.read_text()
        assert 'user = "new@pve"' in text

    def test_other_lines_untouched(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(SAMPLE_CONFIG)

        _update_config_key(config_file, "user", "new@pve")

        text = config_file.read_text()
        assert 'host = "test.example.com"' in text
        assert 'token_name = "old-token"' in text
        assert "max_vcpus = 8" in text

    def test_rejects_double_quotes(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(SAMPLE_CONFIG)

        with pytest.raises(ValueError, match="must not contain double quotes"):
            _update_config_key(config_file, "user", 'evil"injection')

    def test_replaces_token_name(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(SAMPLE_CONFIG)

        _update_config_key(config_file, "token_name", "my-new-token")

        text = config_file.read_text()
        assert 'token_name = "my-new-token"' in text
        assert 'user = "old@pam"' in text


class TestSetupCredentials:
    def test_skip_when_user_declines(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(SAMPLE_CONFIG)
        px = {"host": "test.example.com", "user": "old@pam", "token_name": "old-token"}

        with patch("builtins.input", return_value="n"):
            result = setup_credentials(config_file, px)

        assert result["user"] == "old@pam"
        assert result["token_name"] == "old-token"
        # File unchanged
        assert 'user = "old@pam"' in config_file.read_text()

    def test_updates_credentials(self, tmp_path, capsys):
        config_file = tmp_path / "config.toml"
        config_file.write_text(SAMPLE_CONFIG)
        px = {"host": "test.example.com", "user": "old@pam", "token_name": "old-token"}

        inputs = iter(["y", "admin@pam", "my-token"])
        with patch("builtins.input", side_effect=inputs):
            result = setup_credentials(config_file, px)

        assert result["user"] == "admin@pam"
        assert result["token_name"] == "my-token"

        text = config_file.read_text()
        assert 'user = "admin@pam"' in text
        assert 'token_name = "my-token"' in text

    def test_keeps_defaults_on_empty_input(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(SAMPLE_CONFIG)
        px = {"host": "test.example.com", "user": "old@pam", "token_name": "old-token"}

        inputs = iter(["y", "", ""])
        with patch("builtins.input", side_effect=inputs):
            result = setup_credentials(config_file, px)

        assert result["user"] == "old@pam"
        assert result["token_name"] == "old-token"

    def test_prints_secret_tool_command(self, tmp_path, capsys):
        config_file = tmp_path / "config.toml"
        config_file.write_text(SAMPLE_CONFIG)
        px = {"host": "pve.example.com", "user": "old@pam", "token_name": "old-token"}

        inputs = iter(["y", "admin@pam", "tok"])
        with patch("builtins.input", side_effect=inputs):
            setup_credentials(config_file, px)

        output = capsys.readouterr().out
        assert "secret-tool store" in output
        assert "host pve.example.com" in output

    def test_warns_missing_realm(self, tmp_path, capsys):
        config_file = tmp_path / "config.toml"
        config_file.write_text(SAMPLE_CONFIG)
        px = {"host": "test.example.com", "user": "old@pam", "token_name": "old-token"}

        inputs = iter(["y", "norealm", "tok"])
        with patch("builtins.input", side_effect=inputs):
            setup_credentials(config_file, px)

        output = capsys.readouterr().out
        assert "Warning: user should include realm" in output
