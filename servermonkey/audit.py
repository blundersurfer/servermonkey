"""Structured JSONL audit logger for all tool invocations."""

import fcntl
import json
import os
import time
from pathlib import Path
from typing import Any


_AUDIT_DIR = Path(os.path.expanduser("~/.local/share/servermonkey"))
_AUDIT_FILE = _AUDIT_DIR / "audit.jsonl"
_MAX_LOG_SIZE = 10 * 1024 * 1024  # 10 MB — rotate when exceeded


def _ensure_audit_dir() -> None:
    """Create audit directory with 0700 permissions (owner-only access)."""
    if not _AUDIT_DIR.exists():
        _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        os.chmod(str(_AUDIT_DIR), 0o700)
    else:
        # Ensure permissions are correct even if dir already exists
        current = os.stat(str(_AUDIT_DIR)).st_mode & 0o777
        if current != 0o700:
            os.chmod(str(_AUDIT_DIR), 0o700)


def _rotate_if_needed() -> None:
    """Simple log rotation: rename to .1 if over size limit."""
    try:
        if _AUDIT_FILE.exists() and _AUDIT_FILE.stat().st_size > _MAX_LOG_SIZE:
            rotated = _AUDIT_FILE.with_suffix(".jsonl.1")
            os.replace(str(_AUDIT_FILE), str(rotated))
    except OSError:
        pass  # Best-effort rotation; don't block logging


def log_tool_call(
    tool: str,
    params: dict[str, Any],
    result: Any = None,
    error: str | None = None,
) -> None:
    """Append a structured audit entry to the JSONL log."""
    _ensure_audit_dir()
    _rotate_if_needed()

    entry = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "epoch": time.time(),
        "tool": tool,
        "params": _redact_params(params),
    }
    if error is not None:
        entry["error"] = error
    else:
        entry["result"] = _summarize(result)

    line = json.dumps(entry, default=str) + "\n"

    # Atomic file creation with correct permissions (no TOCTOU race).
    # O_CREAT|O_APPEND|O_WRONLY with 0o600 ensures the file is created
    # with owner-only permissions from the start.
    fd = os.open(str(_AUDIT_FILE), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            os.write(fd, line.encode())
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


_SENSITIVE_KEYS = ("password", "token", "secret", "key")

# Fields that should be logged but truncated (e.g., command args could be long)
_TRUNCATE_KEYS = ("args", "command")
_TRUNCATE_MAX = 200


def _redact_params(params: dict[str, Any]) -> dict[str, Any]:
    """Redact known-sensitive fields and truncate long values from logged params."""
    redacted = {}
    for k, v in params.items():
        k_lower = k.lower()
        if isinstance(v, str) and any(s in k_lower for s in _SENSITIVE_KEYS):
            redacted[k] = "[REDACTED]"
        elif k_lower in _TRUNCATE_KEYS and isinstance(v, str) and len(v) > _TRUNCATE_MAX:
            redacted[k] = v[:_TRUNCATE_MAX] + "...[truncated]"
        elif k_lower in _TRUNCATE_KEYS and isinstance(v, list):
            # Truncate arg lists to prevent log bloat
            serialized = str(v)
            if len(serialized) > _TRUNCATE_MAX:
                redacted[k] = v[:5]  # Keep first 5 args for debugging
            else:
                redacted[k] = v
        else:
            redacted[k] = v
    return redacted


def _summarize(result: Any) -> Any:
    """Keep audit entries compact — truncate large results."""
    if isinstance(result, str) and len(result) > 1000:
        return result[:1000] + "...[truncated]"
    if isinstance(result, list) and len(result) > 20:
        return {"count": len(result), "first_5": result[:5]}
    if isinstance(result, dict):
        serialized = json.dumps(result, default=str)
        if len(serialized) > 2000:
            return {"_keys": list(result.keys()), "_truncated": True}
    return result
