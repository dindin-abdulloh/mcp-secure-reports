"""Encrypted store for the logins the backend uses on the legacy system.

Credentials are only read by the backend. They are never returned from a tool,
so they never reach the model.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from cryptography.fernet import Fernet, InvalidToken


class VaultError(Exception):
    pass


class CredentialNotFoundError(VaultError):
    pass


@dataclass
class StoredCredential:
    system: str
    username: str
    password: str

    def __repr__(self) -> str:  # keep passwords out of tracebacks and logs
        return f"StoredCredential(system={self.system!r}, username={self.username!r}, password='***')"


class CredentialVault:
    """Fernet encrypted JSON file, one encrypted entry per system.

    The interface is kept small (set, get, list, delete) so the file backend
    can later be swapped for HashiCorp Vault or a cloud KMS without touching
    callers.
    """

    def __init__(
        self,
        master_key: str,
        store_path: Path,
        audit_hook: Optional[Callable[[str, str], None]] = None,
    ):
        if not master_key:
            raise VaultError("VAULT_MASTER_KEY is not set")
        self._fernet = Fernet(master_key.encode())
        self._store_path = store_path
        self._audit_hook = audit_hook
        self._store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._store_path.exists():
            self._write_store({})

    def _read_store(self) -> dict:
        return json.loads(self._store_path.read_text(encoding="utf-8"))

    def _write_store(self, data: dict) -> None:
        self._store_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _audit(self, event: str, system: str) -> None:
        if self._audit_hook:
            self._audit_hook(event, system)

    def set_credential(self, system: str, username: str, password: str) -> None:
        store = self._read_store()
        payload = json.dumps({"username": username, "password": password}).encode()
        store[system] = self._fernet.encrypt(payload).decode()
        self._write_store(store)
        self._audit("vault_credential_set", system)

    def get_credential(self, system: str) -> StoredCredential:
        token = self._read_store().get(system)
        if token is None:
            raise CredentialNotFoundError(f"No credential stored for system '{system}'")
        try:
            payload = json.loads(self._fernet.decrypt(token.encode()).decode())
        except InvalidToken as exc:
            raise VaultError(f"Could not decrypt credential for '{system}'. Wrong master key?") from exc
        self._audit("vault_credential_accessed", system)
        return StoredCredential(system=system, username=payload["username"], password=payload["password"])

    def has_credential(self, system: str) -> bool:
        return system in self._read_store()

    def list_systems(self) -> list[str]:
        return sorted(self._read_store().keys())

    def delete_credential(self, system: str) -> None:
        store = self._read_store()
        if system in store:
            del store[system]
            self._write_store(store)
            self._audit("vault_credential_deleted", system)
