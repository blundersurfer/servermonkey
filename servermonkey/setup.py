"""Interactive setup for ServerMonkey — provisions CA certificate."""

from servermonkey.config import find_config, load_config
from servermonkey.credentials import setup_ca_cert


def main():
    config_path = find_config()
    print(f"Using config: {config_path}")

    config = load_config()
    px = config["proxmox"]
    setup_ca_cert(px["host"], px["ca_cert_path"])
    print("\nSetup complete. You can now start the MCP server.")


if __name__ == "__main__":
    main()
