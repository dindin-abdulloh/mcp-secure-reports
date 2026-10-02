import json

from secure_reports_mcp.audit import AuditLogger, redact


def test_redact_masks_sensitive_fields():
    out = redact({"patient_id": "0012345678", "national_id": "3201010101010001", "report_type": "monthly_visits"})
    assert out["patient_id"] == "00******78"
    assert out["national_id"] != "3201010101010001"
    assert out["report_type"] == "monthly_visits"


def test_redact_handles_short_values():
    assert redact({"patient_id": "12"})["patient_id"] == "**"


def test_redact_masks_nested_fields():
    out = redact({"filters": {"patient_id": "0012345678"}, "rows": [{"medical_record_number": "MR123456"}]})
    assert "0012345678" not in json.dumps(out)
    assert "MR123456" not in json.dumps(out)


def test_redact_leaves_none_alone():
    assert redact({"patient_id": None})["patient_id"] is None


def test_log_tool_call_writes_masked_jsonl(tmp_path):
    logger = AuditLogger(tmp_path / "audit.jsonl")
    logger.log_tool_call(
        user_id="u1",
        role="finance",
        tool_name="check_claim_status",
        params={"patient_id": "0012345678"},
        result_status="success",
        duration_ms=12.3,
        session_id="s1",
    )
    record = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip())
    assert record["event_type"] == "tool_call"
    assert "0012345678" not in record["params"]["patient_id"]
    assert "timestamp" in record and "log_id" in record


def test_automation_failure_sets_alert_flag(tmp_path):
    logger = AuditLogger(tmp_path / "audit.jsonl")
    logger.log_automation_failure("download_report", "SELECTOR_NOT_FOUND", "export button missing")
    record = json.loads((tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip())
    assert record["alert"] is True
    assert record["failure_code"] == "SELECTOR_NOT_FOUND"


def test_log_is_append_only(tmp_path):
    logger = AuditLogger(tmp_path / "audit.jsonl")
    for i in range(3):
        logger.log_event("test_event", f"event {i}")
    assert len((tmp_path / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()) == 3
