"""Interactive setup for ServerMonkey — provisions CA certificate."""

import re
from pathlib import Path

from servermonkey.config import find_config, load_config
from servermonkey.credentials import setup_ca_cert


def _update_config_key(config_path: Path, key: str, value: str) -> None:
    """Replace a key = "..." line in config.toml."""
    if '"' in value:
        raise ValueError(f"Value for {key!r} must not contain double quotes")
    text = config_path.read_text()
    pattern = re.compile(rf'^(\s*{re.escape(key)}\s*=\s*)"[^"]*"', re.MULTILINE)
    new_text = pattern.sub(rf'\g<1>"{value}"', text)
    config_path.write_text(new_text)


def setup_credentials(config_path: Path, px: dict) -> dict:
    """Prompt for Proxmox user and token name, update config.toml."""
    current_user = px.get("user", "")
    current_token = px.get("token_name", "")

    print(f"\nCurrent Proxmox user:       {current_user}")
    print(f"Current API token name:     {current_token}")

    response = input("\nUpdate credentials? [y/N] ").strip().lower()
    if response != "y":
        return px

    new_user = input(f"Proxmox user (e.g. user@pam) [{current_user}]: ").strip()
    if not new_user:
        new_user = current_user
    if "@" not in new_user:
        print("Warning: user should include realm (e.g. user@pam)")

    new_token = input(f"API token name [{current_token}]: ").strip()
    if not new_token:
        new_token = current_token

    _update_config_key(config_path, "user", new_user)
    _update_config_key(config_path, "token_name", new_token)

    px["user"] = new_user
    px["token_name"] = new_token

    print(f"\nUpdated config at {config_path}")
    print(f"\nTo store the API token secret in your keyring, run:")
    print(f"  secret-tool store --label='servermonkey proxmox api token' \\")
    print(f"    application proxmox service api host {px['host']}")
    print(f"  (paste the token secret value when prompted)\n")

    return px


def main():
    config_path = find_config()
    print(f"Using config: {config_path}")

    config = load_config()
    px = config["proxmox"]
    px = setup_credentials(config_path, px)
    setup_ca_cert(px["host"], px["ca_cert_path"])
    print("\nSetup complete. You can now start the MCP server.")


if __name__ == "__main__":
    main()
