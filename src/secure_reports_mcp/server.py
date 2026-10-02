"""Role gated MCP server.

One process serves one role (MCP_ROLE). Tools the role may not use are never
registered, so the model does not even see them in tools/list. Every call that
does happen is checked again and written to the audit log.

Run: python -m secure_reports_mcp.server
"""
from __future__ import annotations

import functools
import os
import time
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import tools
from .audit import AuditLogger
from .backend import MockBackend, PlaywrightBackend
from .config import load_config
from .vault import CredentialVault, VaultError

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = Path(os.getenv("CONFIG_PATH", PROJECT_ROOT / "config" / "roles.json"))
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data"))
ROLE = os.getenv("MCP_ROLE", "reporting_staff")
USER = os.getenv("MCP_USER", "demo_user")
BACKEND = os.getenv("BACKEND", "mock")
SESSION_ID = str(uuid.uuid4())

CONFIG = load_config(CONFIG_PATH)
if ROLE not in CONFIG["roles"]:
    raise RuntimeError(f"Role '{ROLE}' from MCP_ROLE is not defined in {CONFIG_PATH}")

SYSTEM = CONFIG.get("system", "legacy_system")
ALLOWED_TOOLS: set[str] = set(CONFIG["roles"][ROLE]["allowed_tools"])
ALLOWED_REPORT_TYPES: set[str] = set(CONFIG["roles"][ROLE].get("allowed_report_types", []))

audit = AuditLogger(DATA_DIR / "audit.jsonl")
vault = CredentialVault(
    master_key=os.getenv("VAULT_MASTER_KEY", ""),
    store_path=DATA_DIR / "vault.json",
    audit_hook=lambda event, system: audit.log_event(event, system),
)

if BACKEND == "playwright":
    backend = PlaywrightBackend(vault, SYSTEM, DATA_DIR / "exports")
else:
    backend = MockBackend(
        vault, SYSTEM, DATA_DIR / "exports", delay_seconds=float(os.getenv("MOCK_DELAY_SECONDS", "2"))
    )
    if not vault.has_credential(SYSTEM):
        # Demo only: store a fake login so the mock flow works out of the box.
        vault.set_credential(SYSTEM, "demo_service_account", "not-a-real-password")

mcp = MCPServer("secure-reports")


# Errors the model is allowed to read. Anything else is reported as a generic
# failure and its details stay in the server log.
_EXPECTED_ERRORS = (PermissionError, ValueError, KeyError, VaultError, NotImplementedError)


def audited(tool_name: str):
    """Check the role again at call time and log every call, success or not."""

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(**kwargs):
            start = time.monotonic()
            status, error = "success", None
            try:
                if tool_name not in ALLOWED_TOOLS:
                    raise PermissionError(f"Role '{ROLE}' may not use '{tool_name}'")
                return fn(**kwargs)
            except _EXPECTED_ERRORS as exc:
                status, error = "failed", str(exc)
                raise ToolError(str(exc).strip("'")) from exc
            except Exception as exc:
                status, error = "failed", repr(exc)
                raise
            finally:
                audit.log_tool_call(
                    user_id=USER,
                    role=ROLE,
                    tool_name=tool_name,
                    params=kwargs,
                    result_status=status,
                    duration_ms=(time.monotonic() - start) * 1000,
                    session_id=SESSION_ID,
                    error_detail=error,
                )

        return wrapper

    return decorator


# Each tool is registered only when the active role allows it.

if "list_available_reports" in ALLOWED_TOOLS:

    @mcp.tool()
    @audited("list_available_reports")
    def list_available_reports(domain: str) -> dict:
        """List the report types this role may download. domain is 'management' or 'billing'."""
        return tools.list_available_reports(domain, ALLOWED_REPORT_TYPES)


if "download_report" in ALLOWED_TOOLS:

    @mcp.tool()
    @audited("download_report")
    def download_report(report_type: str, date_range: dict) -> dict:
        """Start exporting a report. date_range is {"from": "YYYY-MM-DD", "to": "YYYY-MM-DD"}. Returns a job_id."""
        return tools.download_report(backend, report_type, date_range, ALLOWED_REPORT_TYPES)


if "get_report_job_status" in ALLOWED_TOOLS:

    @mcp.tool()
    @audited("get_report_job_status")
    def get_report_job_status(job_id: str) -> dict:
        """Check whether an export job has finished and where the file is."""
        return tools.get_report_job_status(backend, job_id)


if "check_claim_status" in ALLOWED_TOOLS:

    @mcp.tool()
    @audited("check_claim_status")
    def check_claim_status(claim_id: Optional[str] = None, patient_id: Optional[str] = None) -> dict:
        """Look up one insurance claim by claim_id or patient_id."""
        return tools.check_claim_status(claim_id, patient_id)


if "download_billing_statement" in ALLOWED_TOOLS:

    @mcp.tool()
    @audited("download_billing_statement")
    def download_billing_statement(
        date_range: dict, patient_id: Optional[str] = None, invoice_id: Optional[str] = None
    ) -> dict:
        """Start exporting a billing statement for one patient or invoice. Returns a job_id."""
        return tools.download_billing_statement(backend, date_range, patient_id, invoice_id)


def main() -> None:
    audit.log_event("server_start", f"role={ROLE} backend={BACKEND}", session_id=SESSION_ID)
    mcp.run()


if __name__ == "__main__":
    main()
