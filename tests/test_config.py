import json
from pathlib import Path

import pytest

from secure_reports_mcp.config import ConfigError, load_config


def _write(tmp_path, data):
    path = tmp_path / "roles.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_project_config_loads():
    data = load_config(Path(__file__).resolve().parents[1] / "config" / "roles.json")
    assert {"reporting_staff", "unit_manager", "finance"} <= data["roles"].keys()


def test_missing_file_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(tmp_path / "missing.json")


def test_missing_required_key_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, {"tools": {}, "roles": {}}))


def test_role_with_unknown_tool_raises(tmp_path):
    path = _write(tmp_path, {
        "config_version": "1",
        "tools": {"tool_a": {}},
        "roles": {"role_x": {"allowed_tools": ["tool_a", "tool_b"]}},
    })
    with pytest.raises(ConfigError):
        load_config(path)


def test_minimal_config_loads(tmp_path):
    path = _write(tmp_path, {
        "config_version": "1",
        "tools": {"tool_a": {}},
        "roles": {"role_x": {"allowed_tools": ["tool_a"]}},
    })
    assert load_config(path)["roles"]["role_x"]["allowed_tools"] == ["tool_a"]
