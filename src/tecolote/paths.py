from __future__ import annotations

import os
from pathlib import Path


def config_dir() -> Path:
    override = os.environ.get("TECOLOTE_CONFIG_HOME")
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "tecolote"


def state_dir() -> Path:
    override = os.environ.get("TECOLOTE_STATE_HOME")
    if override:
        return Path(override).expanduser()
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "tecolote"


def config_path() -> Path:
    override = os.environ.get("TECOLOTE_CONFIG_FILE")
    return Path(override).expanduser() if override else config_dir() / "config.json"


def default_output_dir() -> Path:
    return Path.home() / "Documents" / "Tecolote" / "Invoices"
