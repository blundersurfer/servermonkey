"""Credential retrieval from libsecret and CA cert management."""

import hashlib
import os
import ssl
import socket
import sys
from pathlib import Path

import gi

gi.require_version("Secret", "1")
from gi.repository import Secret  # noqa: E402


# Schema for looking up the Proxmox API token in libsecret
_SCHEMA = Secret.Schema.new(
    "org.freedesktop.Secret.Generic",
    Secret.SchemaFlags.NONE,
    {
        "application": Secret.SchemaAttributeType.STRING,
        "service": Secret.SchemaAttributeType.STRING,
        "host": Secret.SchemaAttributeType.STRING,
    },
)


def get_api_token(host: str) -> str:
    """Retrieve the Proxmox API token from libsecret.

    Looks up by attributes: application=proxmox, service=api, host=<host>.
    """
    token = Secret.password_lookup_sync(
        _SCHEMA,
        {"application": "proxmox", "service": "api", "host": host},
        None,
    )
    if not token:
        raise RuntimeError(
            f"No API token found in libsecret for the configured host. "
            "Store it with: secret-tool store --label='devai proxmox api token' "
            "application proxmox service api host <hostname>"
        )
    return token


def ensure_ca_cert(ca_cert_path: str) -> str:
    """Verify the CA cert file exists. Raises if not provisioned.

    Returns the resolved path to the CA cert file.
    Use `python -m servermonkey.setup` to provision the cert interactively.
    """
    path = Path(os.path.expanduser(ca_cert_path))

    if path.exists():
        return str(path)

    raise RuntimeError(
        f"CA certificate not found at {path}. "
        "Run 'python -m servermonkey.setup' to fetch and pin the server certificate interactively."
    )


def _fetch_server_cert(host: str, port: int = 8006) -> bytes:
    """Fetch the DER-encoded certificate from a TLS server."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    with socket.create_connection((host, port), timeout=10) as sock:
        with ctx.wrap_socket(sock, server_hostname=host) as tls_sock:
            return tls_sock.getpeercert(binary_form=True)


def _cert_fingerprint(der_cert: bytes) -> str:
    """Compute SHA-256 fingerprint of a DER-encoded certificate."""
    digest = hashlib.sha256(der_cert).hexdigest()
    return ":".join(digest[i:i + 2] for i in range(0, len(digest), 2)).upper()


def setup_ca_cert(host: str, ca_cert_path: str, port: int = 8006) -> str:
    """Interactive CA cert setup: fetch cert, show fingerprint, require confirmation.

    Must be called from an interactive terminal (not from the MCP server).
    Returns the path where the cert was saved.
    """
    path = Path(os.path.expanduser(ca_cert_path))

    if path.exists():
        # Show existing cert fingerprint
        existing_pem = path.read_text()
        existing_der = ssl.PEM_cert_to_DER_cert(existing_pem)
        fp = _cert_fingerprint(existing_der)
        print(f"CA certificate already exists at {path}")
        print(f"  SHA-256 fingerprint: {fp}")

        response = input("Replace it? [y/N] ").strip().lower()
        if response != "y":
            print("Keeping existing certificate.")
            return str(path)

    print(f"Connecting to {host}:{port} to fetch server certificate...")
    der_cert = _fetch_server_cert(host, port)
    fp = _cert_fingerprint(der_cert)

    print()
    print(f"  Host:        {host}:{port}")
    print(f"  SHA-256:     {fp}")
    print()
    print("Verify this fingerprint matches your Proxmox server.")
    print("  On the Proxmox host, run:")
    print(f"    openssl x509 -in /etc/pve/pve-root-ca.pem -noout -sha256 -fingerprint")
    print()

    response = input("Trust this certificate? [y/N] ").strip().lower()
    if response != "y":
        print("Aborted. Certificate was NOT saved.")
        sys.exit(1)

    path.parent.mkdir(parents=True, exist_ok=True)
    pem_cert = ssl.DER_cert_to_PEM_cert(der_cert)
    path.write_text(pem_cert)
    os.chmod(str(path), 0o600)

    print(f"Certificate saved to {path}")
    return str(path)
