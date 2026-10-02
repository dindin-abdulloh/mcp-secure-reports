"""Loads config/roles.json, the single source of truth for which role may use
which tool. Keeping this in a reviewed JSON file means a permission change is a
pull request, not a code change."""
from __future__ import annotations

import json
from pathlib import Path

_REQUIRED_KEYS = {"config_version", "tools", "roles"}


class ConfigError(Exception):
    pass


def load_config(path: Path) -> dict:
    if not path.exists():
        raise ConfigError(f"Config file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    missing = _REQUIRED_KEYS - data.keys()
    if missing:
        raise ConfigError(f"Config {path} is missing required keys: {sorted(missing)}")
    for role, role_cfg in data["roles"].items():
        unknown = set(role_cfg.get("allowed_tools", [])) - set(data["tools"].keys())
        if unknown:
            raise ConfigError(f"Role '{role}' allows tools that are not defined: {sorted(unknown)}")
    return data
