"""Offline account identity and local account-list persistence."""

import hashlib
import json
import os
import tempfile
import uuid
from pathlib import Path

ACCOUNTS_PATH = Path.home() / ".revomc" / "accounts.json"


def offline_uuid(username: str) -> str:
    """Return the UUID v3 used by Minecraft's OfflinePlayer identity."""
    if not isinstance(username, str) or not username:
        raise ValueError("An offline username is required.")
    digest = hashlib.md5(
        f"OfflinePlayer:{username}".encode("utf-8"),
        usedforsecurity=False,
    ).digest()
    return str(uuid.UUID(bytes=digest, version=3))


def load_accounts() -> list[dict]:
    if not ACCOUNTS_PATH.exists():
        return []
    try:
        data = json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read offline accounts: {exc}") from exc
    if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
        raise RuntimeError("The offline account file has an invalid structure.")
    return data


def save_accounts(accounts: list[dict]) -> None:
    ACCOUNTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".accounts-", suffix=".tmp", dir=ACCOUNTS_PATH.parent
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            json.dump(accounts, output, indent=2)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, ACCOUNTS_PATH)
    finally:
        temporary_path.unlink(missing_ok=True)
