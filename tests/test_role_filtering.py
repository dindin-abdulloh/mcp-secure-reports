"""tools/list must differ per role. Each case runs in a subprocess because the
server reads MCP_ROLE once at startup, the same way it runs in production:
one server process per role."""
import json
import os
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]

_LIST_TOOLS = """
import asyncio, json
from secure_reports_mcp import server

async def main():
    tools = await server.mcp.list_tools()
    print(json.dumps(sorted(t.name for t in tools)))

asyncio.run(main())
"""


def _env(tmp_path, role):
    return {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "MCP_ROLE": role,
        "VAULT_MASTER_KEY": Fernet.generate_key().decode(),
        "DATA_DIR": str(tmp_path),
        "BACKEND": "mock",
    }


def _tools_for(role, tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", _LIST_TOOLS], cwd=ROOT, env=_env(tmp_path, role),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_reporting_staff_sees_three_tools(tmp_path):
    assert _tools_for("reporting_staff", tmp_path) == [
        "download_report", "get_report_job_status", "list_available_reports",
    ]


def test_unit_manager_can_check_claims_but_not_statements(tmp_path):
    names = _tools_for("unit_manager", tmp_path)
    assert "check_claim_status" in names
    assert "download_billing_statement" not in names


def test_finance_sees_all_five_tools(tmp_path):
    assert len(_tools_for("finance", tmp_path)) == 5


def test_unknown_role_refuses_to_start(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", "from secure_reports_mcp import server"], cwd=ROOT,
        env=_env(tmp_path, "intern"), capture_output=True, text=True, timeout=60,
    )
    assert result.returncode != 0
    assert "not defined" in result.stderr


_DENIED_CALL = """
import asyncio, json
from mcp.server.mcpserver.exceptions import ToolError
from secure_reports_mcp import server

async def main():
    try:
        await server.mcp.call_tool("download_report", {
            "report_type": "insurance_claims",
            "date_range": {"from": "2026-09-01", "to": "2026-09-30"},
        })
        print(json.dumps({"raised": False}))
    except ToolError as exc:
        print(json.dumps({"raised": True, "message": str(exc)}))

asyncio.run(main())
"""


def test_denied_report_type_returns_clear_error_and_is_audited(tmp_path):
    result = subprocess.run(
        [sys.executable, "-c", _DENIED_CALL], cwd=ROOT, env=_env(tmp_path, "reporting_staff"),
        capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.strip().splitlines()[-1])
    assert out["raised"] is True
    assert "not allowed for this role" in out["message"]
    records = [json.loads(line) for line in (tmp_path / "audit.jsonl").read_text(encoding="utf-8").splitlines()]
    calls = [r for r in records if r["event_type"] == "tool_call"]
    assert calls[-1]["tool_name"] == "download_report"
    assert calls[-1]["result_status"] == "failed"
