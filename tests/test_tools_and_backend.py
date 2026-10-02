import csv
import time

import pytest
from cryptography.fernet import Fernet

from secure_reports_mcp import tools
from secure_reports_mcp.backend import JobStatus, MockBackend
from secure_reports_mcp.vault import CredentialNotFoundError, CredentialVault

RANGE = {"from": "2026-09-01", "to": "2026-09-30"}


@pytest.fixture
def setup(tmp_path):
    events = []
    vault = CredentialVault(
        Fernet.generate_key().decode(), tmp_path / "vault.json", audit_hook=lambda e, s: events.append(e)
    )
    vault.set_credential("his", "svc", "pw")
    backend = MockBackend(vault, "his", tmp_path / "exports", delay_seconds=0)
    return backend, events


def test_list_reports_filters_by_role():
    out = tools.list_available_reports("management", {"monthly_visits"})
    assert out["reports"] == ["monthly_visits"]


def test_list_reports_wildcard_sees_all():
    out = tools.list_available_reports("management", {"*"})
    assert set(out["reports"]) == {"monthly_visits", "bed_occupancy", "finance_summary"}


def test_list_reports_unknown_domain():
    with pytest.raises(ValueError):
        tools.list_available_reports("pharmacy", {"*"})


def test_download_denied_for_report_outside_role(setup):
    backend, _ = setup
    with pytest.raises(PermissionError):
        tools.download_report(backend, "finance_summary", RANGE, {"monthly_visits"})


def test_download_requires_full_date_range(setup):
    backend, _ = setup
    with pytest.raises(ValueError):
        tools.download_report(backend, "monthly_visits", {"from": "2026-09-01"}, {"*"})


def test_job_lifecycle_writes_csv_and_reads_vault(setup):
    backend, events = setup
    job = tools.download_report(backend, "monthly_visits", RANGE, {"*"})
    status = tools.get_report_job_status(backend, job["job_id"])
    assert status["status"] == JobStatus.SUCCESS.value
    with open(status["file_path"], encoding="utf-8") as f:
        rows = list(csv.reader(f))
    assert rows[0] == ["department", "visits", "new_patients"]
    assert len(rows) == 6
    assert "vault_credential_accessed" in events


def test_job_stays_running_until_delay(tmp_path):
    vault = CredentialVault(Fernet.generate_key().decode(), tmp_path / "vault.json")
    vault.set_credential("his", "svc", "pw")
    backend = MockBackend(vault, "his", tmp_path / "exports", delay_seconds=60)
    job_id = backend.start_job("bed_occupancy", RANGE)
    assert backend.get_job(job_id).status == JobStatus.RUNNING


def test_missing_credential_blocks_job(tmp_path):
    vault = CredentialVault(Fernet.generate_key().decode(), tmp_path / "vault.json")
    backend = MockBackend(vault, "his", tmp_path / "exports", delay_seconds=0)
    with pytest.raises(CredentialNotFoundError):
        backend.start_job("monthly_visits", RANGE)


def test_same_range_gives_same_sample(setup):
    backend, _ = setup
    a = tools.get_report_job_status(backend, backend.start_job("finance_summary", RANGE))["file_path"]
    time.sleep(0.01)
    b = tools.get_report_job_status(backend, backend.start_job("finance_summary", RANGE))["file_path"]
    assert open(a, encoding="utf-8").read() == open(b, encoding="utf-8").read()


def test_claim_status_needs_an_identifier():
    with pytest.raises(ValueError):
        tools.check_claim_status()
