"""Tool logic. Pure functions with explicit dependencies, so they are easy to
test. Registration, role filtering and audit logging live in server.py."""
from __future__ import annotations

import time
from typing import Optional

from .backend import ReportBackend

REPORT_CATALOG = {
    "management": ["monthly_visits", "bed_occupancy", "finance_summary"],
    "billing": ["insurance_claims"],
}


def _is_allowed(report_type: str, allowed: set[str]) -> bool:
    return "*" in allowed or report_type in allowed


def list_available_reports(domain: str, allowed_report_types: set[str]) -> dict:
    if domain not in REPORT_CATALOG:
        raise ValueError(f"Unknown domain '{domain}'. Choose one of {sorted(REPORT_CATALOG)}")
    reports = [r for r in REPORT_CATALOG[domain] if _is_allowed(r, allowed_report_types)]
    return {"domain": domain, "reports": reports}


def download_report(
    backend: ReportBackend, report_type: str, date_range: dict, allowed_report_types: set[str]
) -> dict:
    if not _is_allowed(report_type, allowed_report_types):
        raise PermissionError(f"Report type '{report_type}' is not allowed for this role")
    if not {"from", "to"} <= date_range.keys():
        raise ValueError("date_range needs 'from' and 'to' (YYYY-MM-DD)")
    job_id = backend.start_job(report_type, date_range)
    return {"job_id": job_id, "status": "queued", "next": "poll get_report_job_status"}


def get_report_job_status(backend: ReportBackend, job_id: str) -> dict:
    job = backend.get_job(job_id)
    return {
        "job_id": job.job_id,
        "status": job.status.value,
        "file_path": job.file_path,
        "error_detail": job.error_detail,
    }


def check_claim_status(claim_id: Optional[str] = None, patient_id: Optional[str] = None) -> dict:
    if not claim_id and not patient_id:
        raise ValueError("Provide claim_id or patient_id")
    # Synthetic answer. A real backend would look this up in the claims screen.
    return {
        "claim_id": claim_id or "CLAIM-DEMO-0001",
        "status": "in_review",
        "insurer": "Demo Health Insurance",
        "last_updated": time.strftime("%Y-%m-%d"),
    }


def download_billing_statement(
    backend: ReportBackend, date_range: dict, patient_id: Optional[str] = None, invoice_id: Optional[str] = None
) -> dict:
    if not patient_id and not invoice_id:
        raise ValueError("Provide patient_id or invoice_id")
    job_id = backend.start_job("billing_statement", date_range)
    return {"job_id": job_id, "status": "queued", "next": "poll get_report_job_status"}
