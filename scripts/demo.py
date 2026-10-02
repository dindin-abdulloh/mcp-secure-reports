"""End to end demo over the real MCP protocol (stdio).

Starts the server twice, once as reporting_staff and once as finance, and
shows what each role can see and do. Then prints the audit log.

Run: python scripts/demo.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
RANGE = {"from": "2026-09-01", "to": "2026-09-30"}


def _params(role: str, data_dir: Path, key: str) -> StdioServerParameters:
    return StdioServerParameters(
        command=sys.executable,
        args=["-m", "secure_reports_mcp.server"],
        cwd=str(ROOT),
        env={
            "PYTHONPATH": str(ROOT / "src"),
            "MCP_ROLE": role,
            "MCP_USER": f"{role}_demo",
            "VAULT_MASTER_KEY": key,
            "DATA_DIR": str(data_dir),
            "BACKEND": "mock",
            "MOCK_DELAY_SECONDS": "1",
        },
    )


def _text(result) -> str:
    return "\n".join(getattr(c, "text", "") for c in result.content)


def _compact(text: str) -> str:
    try:
        return json.dumps(json.loads(text))
    except ValueError:
        return text


async def _call(session: ClientSession, name: str, args: dict) -> dict | None:
    result = await session.call_tool(name, args)
    label = "error" if result.is_error else "ok"
    print(f"  > {name}({json.dumps(args)})")
    print(f"    {label}: {_compact(_text(result))}")
    return None if result.is_error else json.loads(_text(result))


async def run_as(role: str, data_dir: Path, key: str, steps) -> None:
    print(f"\n=== Connected as {role} ===")
    async with stdio_client(_params(role, data_dir, key)) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            print("  tools/list:", ", ".join(sorted(t.name for t in tools.tools)))
            await steps(session)


async def staff_steps(session: ClientSession) -> None:
    await _call(session, "list_available_reports", {"domain": "management"})
    job = await _call(session, "download_report", {"report_type": "monthly_visits", "date_range": RANGE})
    # insurance_claims is not in reporting_staff's allowed_report_types
    await _call(session, "download_report", {"report_type": "insurance_claims", "date_range": RANGE})
    await asyncio.sleep(1.2)
    status = await _call(session, "get_report_job_status", {"job_id": job["job_id"]})
    print("\n  Exported file:")
    print("    " + Path(status["file_path"]).read_text(encoding="utf-8").replace("\n", "\n    ").rstrip())


async def finance_steps(session: ClientSession) -> None:
    await _call(session, "check_claim_status", {"patient_id": "0012345678"})


async def main() -> None:
    key = Fernet.generate_key().decode()
    with tempfile.TemporaryDirectory() as tmp:
        data_dir = Path(tmp)
        await run_as("reporting_staff", data_dir, key, staff_steps)
        await run_as("finance", data_dir, key, finance_steps)

        print("\n=== audit.jsonl ===")
        for line in (data_dir / "audit.jsonl").read_text(encoding="utf-8").splitlines():
            r = json.loads(line)
            if r["event_type"] == "tool_call":
                print(f"  {r['role']:<16} {r['tool_name']:<24} {r['result_status']:<8} {json.dumps(r['params'])}")
            else:
                print(f"  {r['event_type']:<41} {r.get('detail', '')}")


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    asyncio.run(main())
