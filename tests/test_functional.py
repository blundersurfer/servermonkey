"""Functional test: validate MCP server connectivity against live Proxmox.

This test hits the real Proxmox API using credentials from libsecret and
the CA cert on disk.  It validates that the full stack works end-to-end:

    config.toml -> libsecret token -> CA cert -> ProxmoxClient -> API

Run with:
    .venv/bin/pytest tests/test_functional.py -v

Skipped automatically when the Proxmox host is unreachable or credentials
are missing.  Use ``--run-functional`` to force the attempt.
"""

import os
import ssl
import socket
from pathlib import Path

import pytest

from servermonkey import guardrails
from servermonkey.client import ProxmoxClient
from servermonkey.config import load_config
from servermonkey.credentials import (
    _fetch_ca_cert,
    _is_self_signed_pem,
    ensure_ca_cert,
    get_api_token,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_real_config() -> dict:
    """Load real config and re-init guardrails (overrides conftest autouse)."""
    config = load_config()
    guardrails.init(config)
    return config


def _build_client(config: dict | None = None) -> ProxmoxClient:
    """Build a ProxmoxClient from real config + libsecret credentials."""
    if config is None:
        config = _load_real_config()
    px = config["proxmox"]
    token = get_api_token(px["host"])
    ca_path = ensure_ca_cert(px["ca_cert_path"])
    return ProxmoxClient(
        host=px["host"],
        user=px["user"],
        token_name=px["token_name"],
        token_value=token,
        verify_ssl=ca_path,
    )


def _reimport_ca_cert(px: dict) -> str:
    """Re-fetch the CA cert from the server and write it to disk."""
    host = px["host"]
    ca_cert_path = Path(os.path.expanduser(px["ca_cert_path"]))

    der_cert = _fetch_ca_cert(host, 8006)
    pem_cert = ssl.DER_cert_to_PEM_cert(der_cert)

    ca_cert_path.parent.mkdir(parents=True, exist_ok=True)
    ca_cert_path.write_text(pem_cert)
    os.chmod(str(ca_cert_path), 0o600)
    return str(ca_cert_path)


def _try_list_nodes(client: ProxmoxClient) -> list[dict]:
    """Call list_nodes and return the result.  Raises on failure."""
    nodes = client.list_nodes()
    assert isinstance(nodes, list), f"Expected list, got {type(nodes)}"
    assert len(nodes) > 0, "list_nodes returned an empty list"
    node = nodes[0]
    assert "node" in node, f"Node dict missing 'node' key: {node}"
    assert "status" in node, f"Node dict missing 'status' key: {node}"
    return nodes


def _host_reachable(host: str, port: int = 8006, timeout: float = 3) -> bool:
    """Quick TCP check — is the Proxmox API port open?"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------

def _skip_reason() -> str | None:
    """Return a skip reason string, or None if functional tests should run."""
    try:
        config = load_config()
    except FileNotFoundError:
        return "no config.toml found"

    px = config["proxmox"]
    if not _host_reachable(px["host"]):
        return f"Proxmox host {px['host']}:8006 unreachable"

    try:
        get_api_token(px["host"])
    except RuntimeError:
        return f"no API token in libsecret for {px['host']}"

    return None


_skip = _skip_reason()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.functional
@pytest.mark.skipif(_skip is not None, reason=_skip or "")
class TestMCPConnectivity:
    """End-to-end connectivity: reconnect -> list_nodes, with retry."""

    def test_list_nodes_full_retry_sequence(self):
        """Restart MCP, list nodes; retry with cert reimport; retry again.

        Mirrors the manual verification runbook:
        1. Reconnect (fresh client from config + credentials)
        2. list_nodes — if OK, pass
        3. Re-import CA cert, new client, list_nodes — if OK, pass
        4. Full config reload + new client, list_nodes — if OK, pass
        5. All failed — emit diagnostics
        """
        errors: list[str] = []

        # --- Attempt 1: fresh client (simulates MCP restart) ---
        try:
            config = _load_real_config()
            client = _build_client(config)
            nodes = _try_list_nodes(client)
            assert nodes[0]["status"] == "online"
            return  # PASS
        except Exception as e:
            errors.append(f"Attempt 1 (fresh client): {e}")

        # --- Attempt 2: re-import CA cert, then retry ---
        px = config["proxmox"]
        try:
            ca_path = _reimport_ca_cert(px)
            token = get_api_token(px["host"])
            client = ProxmoxClient(
                host=px["host"],
                user=px["user"],
                token_name=px["token_name"],
                token_value=token,
                verify_ssl=ca_path,
            )
            nodes = _try_list_nodes(client)
            return  # PASS
        except Exception as e:
            errors.append(f"Attempt 2 (cert reimport): {e}")

        # --- Attempt 3: full reload (simulates second MCP restart) ---
        try:
            config = _load_real_config()
            client = _build_client(config)
            _try_list_nodes(client)
            return  # PASS
        except Exception as e:
            errors.append(f"Attempt 3 (full reload): {e}")

        # --- All attempts failed ---
        detail = "\n  ".join(errors)
        pytest.fail(
            f"MCP connectivity failed after 3 attempts:\n  {detail}\n\n"
            f"Troubleshooting:\n"
            f"  1. Verify config.toml token_name matches Proxmox "
            f"(Datacenter -> Permissions -> API Tokens)\n"
            f"  2. Verify the API secret is in libsecret:\n"
            f"       secret-tool lookup application proxmox service api "
            f"host {px['host']}\n"
            f"  3. Re-run:  servermonkey-setup\n"
            f"  4. Check host reachable:  "
            f"curl -k https://{px['host']}:8006/api2/json/version\n"
        )

    def test_node_status(self):
        """Verify we can call node_status for the first node.

        A 403 (Forbidden) is acceptable — it proves the connection and
        auth succeeded but the token lacks Sys.Audit.  Only unexpected
        errors (401 Unauthorized, connection failures) should fail.
        """
        from proxmoxer.core import ResourceException

        config = _load_real_config()
        client = _build_client(config)
        nodes = client.list_nodes()
        node_name = nodes[0]["node"]
        try:
            status = client.node_status(node_name)
            assert isinstance(status, dict)
        except ResourceException as e:
            if e.status_code == 403:
                pytest.skip(
                    f"Token lacks Sys.Audit on /nodes/{node_name} "
                    "(connection is OK, permission insufficient)"
                )
            raise
