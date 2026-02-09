"""Configuration loading and validation for ServerMonkey."""

import os
from pathlib import Path
from typing import Any

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]


_CONFIG_PATHS = [
    Path.home() / ".config" / "servermonkey" / "config.toml",
    Path(__file__).parent.parent / "config.toml",
]

_SCRIPTS_DIR_PATHS = [
    Path.home() / ".config" / "servermonkey" / "scripts",
    Path(__file__).parent.parent / "scripts",
]

# Required top-level keys and their required sub-keys
_SCHEMA = {
    "proxmox": {"host", "user", "token_name", "ca_cert_path"},
    "resource_caps": {"max_vcpus", "max_memory_mb", "max_disk_grow_gb"},
}


def _get_search_paths(env_var: str, defaults: list[Path]) -> list[Path]:
    """Build search paths: env var override (if set) + defaults."""
    paths: list[Path] = []
    env_val = os.environ.get(env_var, "").strip()
    if env_val:
        env_path = Path(env_val)
        if env_path.is_absolute():
            paths.append(env_path)
        # Silently ignore relative/empty env values (prevent path traversal)
    paths.extend(defaults)
    return paths


def find_config() -> Path:
    """Return the first existing config file from search paths."""
    candidates = _get_search_paths("SERVERMONKEY_CONFIG", _CONFIG_PATHS)
    for p in candidates:
        if p.is_file():
            return p
    searched = [str(p) for p in candidates]
    raise FileNotFoundError(f"No config.toml found. Searched: {searched}")


def find_scripts_dir() -> Path:
    """Return the first existing scripts directory from search paths."""
    candidates = _get_search_paths("SERVERMONKEY_SCRIPTS", _SCRIPTS_DIR_PATHS)
    for p in candidates:
        if p.is_dir():
            return p
    # Fall back to project-relative scripts dir (may not exist yet)
    return Path(__file__).parent.parent / "scripts"


def load_config() -> dict[str, Any]:
    """Load and validate config from the first found config.toml."""
    config_path = find_config()
    with open(config_path, "rb") as f:
        config = tomllib.load(f)
    validate_schema(config)
    return config


def validate_schema(config: dict[str, Any]) -> None:
    """Validate that required config sections and keys exist."""
    for section, required_keys in _SCHEMA.items():
        if section not in config:
            raise ValueError(f"Config missing required section: [{section}]")
        if not isinstance(config[section], dict):
            raise ValueError(f"Config section [{section}] must be a table")
        missing = required_keys - set(config[section].keys())
        if missing:
            raise ValueError(f"Config [{section}] missing required keys: {missing}")

    # Validate types for resource caps
    caps = config.get("resource_caps", {})
    for key in ("max_vcpus", "max_memory_mb", "max_disk_grow_gb"):
        val = caps.get(key)
        if val is not None and not isinstance(val, int):
            raise ValueError(f"resource_caps.{key} must be an integer, got {type(val).__name__}")
        if val is not None and val <= 0:
            raise ValueError(f"resource_caps.{key} must be positive, got {val}")
