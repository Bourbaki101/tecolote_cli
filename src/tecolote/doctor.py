from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import load_config
from .errors import TecoloteError
from .paths import config_path, state_dir
from .renderer import renderer_available
from .state import load_state, state_path


def _check(ok: bool, code: str | None = None, message: str | None = None) -> dict[str, object]:
    result: dict[str, object] = {"ok": ok}
    if code:
        result["code"] = code
    if message:
        result["message"] = message
    return result


def run_doctor() -> dict[str, Any]:
    checks: dict[str, dict[str, object]] = {}
    config: dict[str, Any] | None = None
    try:
        config = load_config()
        checks["config"] = _check(True, message=str(config_path()))
    except TecoloteError as exc:
        checks["config"] = _check(False, exc.code, exc.message)

    if config:
        signature = Path(str(config["bank"]["signaturePath"]))
        checks["signature"] = (
            _check(True, message="Configured signature is readable.")
            if signature.is_file() and os.access(signature, os.R_OK)
            else _check(False, "SIGNATURE_NOT_FOUND", "Configured signature file does not exist or is unreadable.")
        )
    else:
        checks["signature"] = _check(False, "CONFIG_REQUIRED", "Configuration is required for this check.")

    checks["renderer"] = (
        _check(True, message="ReportLab is available.")
        if renderer_available()
        else _check(False, "PDF_RENDERER_UNAVAILABLE", "ReportLab is not installed.")
    )

    if config:
        output = Path(str(config["invoice"]["outputDirectory"]))
        try:
            output.mkdir(parents=True, exist_ok=True)
            probe = output / ".tecolote-write-check"
            probe.write_bytes(b"")
            probe.unlink()
            checks["outputDirectory"] = _check(True, message=str(output))
        except OSError:
            checks["outputDirectory"] = _check(
                False, "FILESYSTEM_ERROR", "Output directory cannot be created or written."
            )
    else:
        checks["outputDirectory"] = _check(False, "CONFIG_REQUIRED", "Configuration is required for this check.")

    try:
        state_dir().mkdir(parents=True, exist_ok=True, mode=0o700)
        initial = int(config["invoice"]["initialNextNumber"]) if config else 1
        load_state(initial)
        checks["state"] = _check(True, message=str(state_path()))
    except (OSError, TecoloteError) as exc:
        code = exc.code if isinstance(exc, TecoloteError) else "FILESYSTEM_ERROR"
        checks["state"] = _check(False, code, "Persistent state is not accessible.")

    return {"ok": all(bool(check["ok"]) for check in checks.values()), "checks": checks}
