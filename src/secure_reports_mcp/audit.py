"""Append only JSONL audit log. Every tool call is written here, and sensitive
fields are masked before anything touches the disk."""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Optional

SENSITIVE_FIELDS = {"patient_id", "medical_record_number", "national_id"}


def _mask(value: Any) -> str:
    s = str(value)
    if len(s) <= 4:
        return "*" * len(s)
    return s[:2] + "*" * (len(s) - 4) + s[-2:]


def redact(params: Any) -> Any:
    """Mask sensitive fields, including ones nested inside dicts and lists."""
    if isinstance(params, dict):
        return {
            key: (_mask(value) if key in SENSITIVE_FIELDS and value is not None else redact(value))
            for key, value in params.items()
        }
    if isinstance(params, list):
        return [redact(item) for item in params]
    return params


class AuditLogger:
    def __init__(self, log_path: Path):
        self._log_path = log_path
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._log_path

    def _write(self, record: dict) -> None:
        record["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        record["log_id"] = str(uuid.uuid4())
        with self._log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def log_tool_call(
        self,
        *,
        user_id: str,
        role: str,
        tool_name: str,
        params: dict,
        result_status: str,
        duration_ms: float,
        session_id: Optional[str] = None,
        error_detail: Optional[str] = None,
    ) -> None:
        self._write({
            "event_type": "tool_call",
            "user_id": user_id,
            "role": role,
            "tool_name": tool_name,
            "params": redact(params),
            "result_status": result_status,
            "duration_ms": round(duration_ms, 2),
            "session_id": session_id,
            "error_detail": error_detail,
        })

    def log_event(self, event_type: str, detail: str, **extra: Any) -> None:
        self._write({"event_type": event_type, "detail": detail, **extra})

    def log_automation_failure(self, tool_name: str, failure_code: str, detail: str) -> None:
        """failure_code is one of SELECTOR_NOT_FOUND, SESSION_EXPIRED, CAPTCHA_DETECTED, TIMEOUT.

        Automation failures are always flagged with alert=True so a separate
        alerting process can pick them up. Nothing fails silently.
        """
        self._write({
            "event_type": "automation_failure",
            "tool_name": tool_name,
            "failure_code": failure_code,
            "detail": detail,
            "alert": True,
        })
