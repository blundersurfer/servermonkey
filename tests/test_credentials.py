"""Mocked libsecret tests for credential retrieval."""

import ssl
import subprocess
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


def test_ensure_ca_cert_exists(tmp_path, monkeypatch, two_pem_certs):
    """When CA cert already exists and is self-signed, return the path."""
    cert_file = tmp_path / "test-ca.pem"
    cert_file.write_text(two_pem_certs[0])
    result = creds.ensure_ca_cert(str(cert_file))
    assert result == str(cert_file)


def test_ensure_ca_cert_missing_raises(tmp_path):
    """When CA cert doesn't exist, raise with setup instructions."""
    cert_file = tmp_path / "nonexistent.pem"
    with pytest.raises(RuntimeError, match="servermonkey-setup"):
        creds.ensure_ca_cert(str(cert_file))


def test_cert_fingerprint():
    """Test fingerprint computation produces expected format."""
    # SHA-256 of b"test" is known
    fp = creds._cert_fingerprint(b"test")
    assert ":" in fp
    parts = fp.split(":")
    assert len(parts) == 32  # SHA-256 = 32 bytes = 32 hex pairs
    assert all(len(p) == 2 for p in parts)


# --- _fetch_ca_cert tests ---


@pytest.fixture(scope="session")
def two_pem_certs():
    """Generate two valid self-signed PEM certs via openssl for test data."""
    certs = []
    for cn in ("leaf", "ca"):
        result = subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:1024",
                "-keyout", "/dev/null", "-nodes",
                "-subj", f"/CN={cn}", "-days", "1",
            ],
            capture_output=True,
            timeout=10,
        )
        assert result.returncode == 0, f"openssl req failed: {result.stderr.decode()}"
        certs.append(result.stdout.decode().strip())
    return certs  # [leaf_pem, ca_pem]


def _make_openssl_result(stdout: str, returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    """Helper to build a CompletedProcess mimicking openssl s_client output."""
    return subprocess.CompletedProcess(
        args=["openssl"],
        returncode=returncode,
        stdout=stdout.encode(),
        stderr=stderr.encode(),
    )


def test_fetch_ca_cert_chain_returns_last(monkeypatch, two_pem_certs):
    """With 2 certs (leaf + CA), return the last (CA) cert as DER."""
    leaf_pem, ca_pem = two_pem_certs
    stdout = f"some header\n{leaf_pem}\nsome middle\n{ca_pem}\nsome trailer\n"
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: _make_openssl_result(stdout)
    )
    der = creds._fetch_ca_cert("proxmox.example.com")
    expected_der = ssl.PEM_cert_to_DER_cert(ca_pem)
    assert der == expected_der


def test_fetch_ca_cert_single_cert(monkeypatch, two_pem_certs):
    """With 1 cert (self-signed), return that cert as DER."""
    leaf_pem = two_pem_certs[0]
    stdout = f"some header\n{leaf_pem}\nsome trailer\n"
    original_run = subprocess.run

    def patched_run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        if cmd and cmd[0] == "openssl" and len(cmd) > 1 and cmd[1] == "x509":
            return original_run(*args, **kwargs)
        return _make_openssl_result(stdout)

    monkeypatch.setattr(subprocess, "run", patched_run)
    der = creds._fetch_ca_cert("proxmox.example.com")
    expected_der = ssl.PEM_cert_to_DER_cert(leaf_pem)
    assert der == expected_der


def test_fetch_ca_cert_invalid_hostname():
    """Reject hostnames with shell-injection characters."""
    with pytest.raises(ValueError, match="Invalid hostname"):
        creds._fetch_ca_cert("-inject")


def test_fetch_ca_cert_openssl_not_found(monkeypatch):
    """When openssl is not installed, raise RuntimeError."""
    def raise_fnf(*a, **kw):
        raise FileNotFoundError("No such file or directory: 'openssl'")

    monkeypatch.setattr(subprocess, "run", raise_fnf)
    with pytest.raises(RuntimeError, match="openssl CLI not found"):
        creds._fetch_ca_cert("proxmox.example.com")


def test_fetch_ca_cert_nonzero_returncode(monkeypatch):
    """When openssl exits non-zero, raise RuntimeError without raw stderr."""
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: _make_openssl_result("", returncode=1, stderr="connect: Connection refused"),
    )
    with pytest.raises(RuntimeError, match="openssl s_client failed") as exc_info:
        creds._fetch_ca_cert("proxmox.example.com")
    # Raw stderr should NOT be in the exception message
    assert "Connection refused" not in str(exc_info.value)


def test_fetch_ca_cert_empty_output(monkeypatch):
    """When openssl returns no certs, raise RuntimeError."""
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **kw: _make_openssl_result("no certs here\n"),
    )
    with pytest.raises(RuntimeError, match="No certificates received"):
        creds._fetch_ca_cert("proxmox.example.com")


# --- _is_self_signed_pem and non-self-signed leaf tests ---


@pytest.fixture(scope="session")
def ca_signed_leaf_pem(tmp_path_factory):
    """Generate a CA cert and a leaf cert signed by it."""
    tmpdir = tmp_path_factory.mktemp("certs")
    ca_key = tmpdir / "ca.key"
    ca_cert = tmpdir / "ca.pem"
    leaf_key = tmpdir / "leaf.key"
    leaf_csr = tmpdir / "leaf.csr"
    leaf_cert = tmpdir / "leaf.pem"

    # Generate CA key + self-signed cert
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:1024", "-keyout", str(ca_key),
         "-out", str(ca_cert), "-nodes", "-subj", "/CN=TestCA", "-days", "1"],
        capture_output=True, timeout=10, check=True,
    )
    # Generate leaf key + CSR
    subprocess.run(
        ["openssl", "req", "-newkey", "rsa:1024", "-keyout", str(leaf_key),
         "-out", str(leaf_csr), "-nodes", "-subj", "/CN=leaf.example.com"],
        capture_output=True, timeout=10, check=True,
    )
    # Sign leaf with CA
    subprocess.run(
        ["openssl", "x509", "-req", "-in", str(leaf_csr), "-CA", str(ca_cert),
         "-CAkey", str(ca_key), "-CAcreateserial", "-out", str(leaf_cert), "-days", "1"],
        capture_output=True, timeout=10, check=True,
    )
    return leaf_cert.read_text().strip()


def test_is_self_signed_pem_true(two_pem_certs):
    """Self-signed certs (generated with -x509) should return True."""
    assert creds._is_self_signed_pem(two_pem_certs[0]) is True


def test_is_self_signed_pem_false(ca_signed_leaf_pem):
    """A CA-signed leaf cert should return False."""
    assert creds._is_self_signed_pem(ca_signed_leaf_pem) is False


def test_ensure_ca_cert_non_self_signed_raises(tmp_path, ca_signed_leaf_pem):
    """When saved cert is a non-self-signed leaf, raise with instructions to rerun setup."""
    cert_file = tmp_path / "bad-ca.pem"
    cert_file.write_text(ca_signed_leaf_pem)
    with pytest.raises(RuntimeError, match="not self-signed"):
        creds.ensure_ca_cert(str(cert_file))


def test_fetch_ca_cert_single_non_self_signed_raises(monkeypatch, ca_signed_leaf_pem):
    """With a single non-self-signed cert, raise RuntimeError with instructions."""
    stdout = f"some header\n{ca_signed_leaf_pem}\nsome trailer\n"

    original_run = subprocess.run

    def patched_run(*args, **kwargs):
        cmd = args[0] if args else kwargs.get("args", [])
        # Let the openssl x509 call (for _is_self_signed_pem) through to real openssl
        if cmd and cmd[0] == "openssl" and len(cmd) > 1 and cmd[1] == "x509":
            return original_run(*args, **kwargs)
        # Mock the s_client call
        return _make_openssl_result(stdout)

    monkeypatch.setattr(subprocess, "run", patched_run)
    with pytest.raises(RuntimeError, match="leaf certificate"):
        creds._fetch_ca_cert("proxmox.example.com")
