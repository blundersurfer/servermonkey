"""Credential retrieval from libsecret and CA cert management."""

import hashlib
import logging
import os
import re
import subprocess
import ssl
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

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
    """Verify the CA cert file exists and is a valid CA cert. Raises if not provisioned.

    Returns the resolved path to the CA cert file.
    Use `python -m servermonkey.setup` to provision the cert interactively.
    """
    path = Path(os.path.expanduser(ca_cert_path))

    if not path.exists():
        raise RuntimeError(
            f"CA certificate not found at {path}. "
            "Run 'servermonkey-setup' to fetch and pin the server certificate interactively."
        )

    pem_text = path.read_text()
    if not _is_self_signed_pem(pem_text):
        raise RuntimeError(
            f"CA certificate at {path} is not self-signed — it appears to be a leaf certificate. "
            "This will cause SSL verification failures.\n"
            "Run 'servermonkey-setup' to replace it with the correct CA root certificate."
        )

    return str(path)


_HOST_RE = re.compile(r"^[a-zA-Z0-9]([a-zA-Z0-9.\-]{0,253}[a-zA-Z0-9])?$")


def _is_self_signed_pem(pem: str) -> bool:
    """Check if a PEM certificate is self-signed (subject == issuer)."""
    result = subprocess.run(
        ["openssl", "x509", "-noout", "-subject", "-issuer"],
        input=pem.encode(), capture_output=True, timeout=5,
    )
    if result.returncode != 0:
        return False
    lines = result.stdout.decode().strip().splitlines()
    if len(lines) != 2:
        return False
    subject = lines[0].split("=", 1)[1].strip() if "=" in lines[0] else ""
    issuer = lines[1].split("=", 1)[1].strip() if "=" in lines[1] else ""
    return subject == issuer


def _fetch_ca_cert(host: str, port: int = 8006) -> bytes:
    """Fetch the DER-encoded CA certificate from a TLS server.

    Uses openssl s_client to retrieve the full certificate chain and
    returns the last certificate (the CA/root). Falls back to the leaf
    certificate if only one certificate is presented (self-signed setup).
    """
    if not _HOST_RE.match(host):
        raise ValueError(f"Invalid hostname: {host!r}")

    try:
        result = subprocess.run(
            ["openssl", "s_client", "-showcerts", "-connect", f"{host}:{port}"],
            input=b"",
            capture_output=True,
            timeout=10,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "openssl CLI not found. Install openssl to fetch the CA certificate, "
            "or manually place your CA cert at the configured ca_cert_path."
        )

    if result.returncode != 0:
        stderr_msg = result.stderr.decode(errors="replace").strip()
        logger.debug("openssl s_client stderr: %s", stderr_msg)
        raise RuntimeError(
            f"openssl s_client failed (exit {result.returncode}) for {host}:{port}"
        )

    certs_pem: list[str] = []
    lines: list[str] = []
    in_cert = False
    for line in result.stdout.decode().splitlines():
        if "-----BEGIN CERTIFICATE-----" in line:
            in_cert = True
            lines = [line]
        elif "-----END CERTIFICATE-----" in line:
            lines.append(line)
            certs_pem.append("\n".join(lines))
            in_cert = False
        elif in_cert:
            lines.append(line)

    if not certs_pem:
        raise RuntimeError(f"No certificates received from {host}:{port}")

    if len(certs_pem) > 1:
        # Last cert in a full chain is the CA
        return ssl.PEM_cert_to_DER_cert(certs_pem[-1])

    # Single cert — check if self-signed
    if _is_self_signed_pem(certs_pem[0]):
        return ssl.PEM_cert_to_DER_cert(certs_pem[0])

    raise RuntimeError(
        f"Server at {host}:{port} sent only a leaf certificate (not self-signed). "
        "The CA root certificate is required but was not included in the TLS chain.\n"
        "Copy it from the Proxmox host:\n"
        f"  scp root@{host}:/etc/pve/pve-root-ca.pem <local-path>\n"
        "Then run servermonkey-setup again and provide the path when prompted."
    )


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

    print(f"Connecting to {host}:{port} to fetch CA certificate...")
    try:
        der_cert = _fetch_ca_cert(host, port)
    except RuntimeError as e:
        if "leaf certificate" not in str(e):
            raise
        print(f"\n{e}")
        print()
        manual_path = input("Path to CA cert PEM file (or Enter to abort): ").strip()
        if not manual_path:
            print("Aborted.")
            sys.exit(1)
        manual = Path(os.path.expanduser(manual_path))
        if not manual.is_file():
            print(f"File not found: {manual}")
            sys.exit(1)
        pem_text = manual.read_text()
        der_cert = ssl.PEM_cert_to_DER_cert(pem_text)
    fp = _cert_fingerprint(der_cert)

    print()
    print(f"  Host:        {host}:{port}")
    print(f"  SHA-256:     {fp}")
    print()
    print("Verify this fingerprint matches your Proxmox CA certificate.")
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
