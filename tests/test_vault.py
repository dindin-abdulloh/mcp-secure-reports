import pytest
from cryptography.fernet import Fernet

from secure_reports_mcp.vault import CredentialNotFoundError, CredentialVault, VaultError


@pytest.fixture
def vault(tmp_path):
    events = []
    v = CredentialVault(
        master_key=Fernet.generate_key().decode(),
        store_path=tmp_path / "vault.json",
        audit_hook=lambda event, system: events.append((event, system)),
    )
    v.events = events
    return v


def test_set_then_get_roundtrip(vault):
    vault.set_credential("his", "svc_user", "S3cret!")
    cred = vault.get_credential("his")
    assert (cred.username, cred.password) == ("svc_user", "S3cret!")


def test_unknown_system_raises(vault):
    with pytest.raises(CredentialNotFoundError):
        vault.get_credential("missing")


def test_file_on_disk_is_encrypted(vault, tmp_path):
    vault.set_credential("his", "svc_user", "PlainTextPassword")
    raw = (tmp_path / "vault.json").read_text(encoding="utf-8")
    assert "PlainTextPassword" not in raw
    assert "svc_user" not in raw


def test_password_hidden_from_repr(vault):
    vault.set_credential("his", "svc_user", "PlainTextPassword")
    assert "PlainTextPassword" not in repr(vault.get_credential("his"))


def test_audit_hook_on_set_and_get(vault):
    vault.set_credential("his", "u", "p")
    vault.get_credential("his")
    assert ("vault_credential_set", "his") in vault.events
    assert ("vault_credential_accessed", "his") in vault.events


def test_delete_credential(vault):
    vault.set_credential("his", "u", "p")
    vault.delete_credential("his")
    assert not vault.has_credential("his")


def test_wrong_master_key_fails(tmp_path):
    path = tmp_path / "vault.json"
    CredentialVault(Fernet.generate_key().decode(), path).set_credential("his", "u", "p")
    with pytest.raises(VaultError):
        CredentialVault(Fernet.generate_key().decode(), path).get_credential("his")


def test_empty_master_key_raises(tmp_path):
    with pytest.raises(VaultError):
        CredentialVault(master_key="", store_path=tmp_path / "vault.json")
