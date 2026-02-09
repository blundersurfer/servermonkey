"""Mocked libsecret tests for credential retrieval."""

from unittest.mock import MagicMock

import pytest

import servermonkey.credentials as creds


@pytest.fixture
def mock_secret(monkeypatch):
    """Replace the Secret module with a mock, auto-restored by monkeypatch."""
    mock = MagicMock()
    mock.SchemaFlags.NONE = 0
    mock.SchemaAttributeType.STRING = 0
    mock.Schema.new.return_value = MagicMock()
    monkeypatch.setattr(creds, "Secret", mock)
    monkeypatch.setattr(creds, "_SCHEMA", MagicMock())
    return mock


def test_get_api_token_found(mock_secret):
    mock_secret.password_lookup_sync.return_value = "test-token-value"
    token = creds.get_api_token("test.example.com")
    assert token == "test-token-value"


def test_get_api_token_not_found(mock_secret):
    mock_secret.password_lookup_sync.return_value = None
    with pytest.raises(RuntimeError, match="No API token found"):
        creds.get_api_token("test.example.com")


def test_ensure_ca_cert_exists(tmp_path):
    """When CA cert already exists, return the path."""
    cert_file = tmp_path / "test-ca.pem"
    cert_file.write_text("-----BEGIN CERTIFICATE-----\ntest\n-----END CERTIFICATE-----\n")
    result = creds.ensure_ca_cert(str(cert_file))
    assert result == str(cert_file)


def test_ensure_ca_cert_missing_raises(tmp_path):
    """When CA cert doesn't exist, raise with setup instructions."""
    cert_file = tmp_path / "nonexistent.pem"
    with pytest.raises(RuntimeError, match="python -m servermonkey.setup"):
        creds.ensure_ca_cert(str(cert_file))


def test_cert_fingerprint():
    """Test fingerprint computation produces expected format."""
    # SHA-256 of b"test" is known
    fp = creds._cert_fingerprint(b"test")
    assert ":" in fp
    parts = fp.split(":")
    assert len(parts) == 32  # SHA-256 = 32 bytes = 32 hex pairs
    assert all(len(p) == 2 for p in parts)
