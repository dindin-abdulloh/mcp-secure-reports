"""Backends that actually pull reports out of the legacy system.

MockBackend runs the whole flow (vault lookup, async job, file on disk) with
synthetic data, so the server can be tried without access to a real system.
PlaywrightBackend shows where real browser automation plugs in. Both share the
same interface, so tools.py never knows which one it is talking to.
"""
from __future__ import annotations

import csv
import random
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Protocol

from .vault import CredentialVault


class AutomationError(Exception):
    failure_code: str = "UNKNOWN"


class SelectorNotFoundError(AutomationError):
    failure_code = "SELECTOR_NOT_FOUND"


class SessionExpiredError(AutomationError):
    failure_code = "SESSION_EXPIRED"


class CaptchaDetectedError(AutomationError):
    failure_code = "CAPTCHA_DETECTED"


class AutomationTimeoutError(AutomationError):
    failure_code = "TIMEOUT"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class ReportJob:
    job_id: str
    report_type: str
    date_range: dict
    status: JobStatus = JobStatus.QUEUED
    file_path: Optional[str] = None
    error_detail: Optional[str] = None
    created_at: float = field(default_factory=time.monotonic)


class ReportBackend(Protocol):
    def start_job(self, report_type: str, date_range: dict) -> str: ...

    def get_job(self, job_id: str) -> ReportJob: ...


# Synthetic sample data. No real data ships with this repo.
_DEPARTMENTS = ["Internal Medicine", "Pediatrics", "Surgery", "Obstetrics", "Cardiology"]


def _sample_rows(report_type: str, rng: random.Random) -> tuple[list[str], list[list]]:
    if report_type == "monthly_visits":
        return ["department", "visits", "new_patients"], [
            [d, rng.randint(300, 1500), rng.randint(40, 300)] for d in _DEPARTMENTS
        ]
    if report_type == "bed_occupancy":
        rows = []
        for d in _DEPARTMENTS:
            beds = rng.randint(20, 40)
            occupied = rng.randint(beds // 2, beds)
            rows.append([d, beds, occupied, round(occupied * 100 / beds, 1)])
        return ["ward", "beds", "occupied", "occupancy_pct"], rows
    if report_type == "finance_summary":
        categories = ["Outpatient revenue", "Inpatient revenue", "Pharmacy revenue", "Staff costs", "Supplies"]
        return ["category", "amount_usd"], [[c, rng.randint(20_000, 400_000)] for c in categories]
    if report_type == "insurance_claims":
        statuses = ["submitted", "in_review", "approved", "rejected"]
        return ["claim_ref", "insurer", "status", "amount_usd"], [
            [f"CLM-{i:04d}", "Demo Health Insurance", rng.choice(statuses), rng.randint(100, 5_000)]
            for i in range(1, 6)
        ]
    items = ["Consultation", "Lab panel", "Radiology", "Pharmacy", "Room"]
    return ["line", "description", "amount_usd"], [[i + 1, item, rng.randint(20, 900)] for i, item in enumerate(items)]


class MockBackend:
    """Simulates a slow export: the job finishes after `delay_seconds`."""

    def __init__(self, vault: CredentialVault, system: str, export_dir: Path, delay_seconds: float = 2.0):
        self._vault = vault
        self._system = system
        self._export_dir = export_dir
        self._delay = delay_seconds
        self._jobs: dict[str, ReportJob] = {}
        self._export_dir.mkdir(parents=True, exist_ok=True)

    def start_job(self, report_type: str, date_range: dict) -> str:
        # A real backend logs in here. The mock still reads the credential so
        # the vault access shows up in the audit log exactly as it would.
        self._vault.get_credential(self._system)
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = ReportJob(
            job_id=job_id, report_type=report_type, date_range=date_range, status=JobStatus.RUNNING
        )
        return job_id

    def get_job(self, job_id: str) -> ReportJob:
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"Unknown job_id '{job_id}'")
        if job.status == JobStatus.RUNNING and time.monotonic() - job.created_at >= self._delay:
            job.file_path = str(self._write_sample(job))
            job.status = JobStatus.SUCCESS
        return job

    def _write_sample(self, job: ReportJob) -> Path:
        rng = random.Random(f"{job.report_type}:{sorted(job.date_range.items())}")
        header, rows = _sample_rows(job.report_type, rng)
        path = self._export_dir / f"{job.report_type}_{job.job_id[:8]}.csv"
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            writer.writerows(rows)
        return path


class PlaywrightBackend:
    """Where real browser automation goes.

    start_job should: read the login from the vault, open a Playwright
    session, navigate to the export page, download the file, and on any
    AutomationError mark the job FAILED with the failure code so the audit
    log raises an alert. Selectors depend on the target system, so this is
    left unimplemented in the public demo.
    """

    def __init__(self, vault: CredentialVault, system: str, export_dir: Path):
        self._vault = vault
        self._system = system
        self._export_dir = export_dir

    def start_job(self, report_type: str, date_range: dict) -> str:
        raise NotImplementedError("Fill in the selectors for your target system, or run with BACKEND=mock")

    def get_job(self, job_id: str) -> ReportJob:
        raise NotImplementedError
