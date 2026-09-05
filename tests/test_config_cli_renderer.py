from __future__ import annotations

import json
from pathlib import Path

import pytest

from tecolote.cli import main
from tecolote.config import load_config, masked_config
from tecolote.doctor import run_doctor
from tecolote.drafts import create_draft
from tecolote.errors import ValidationError
from tecolote.renderer import render_invoice


def test_missing_and_malformed_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TECOLOTE_CONFIG_HOME", str(tmp_path))
    with pytest.raises(ValidationError) as missing:
        load_config()
    assert missing.value.code == "CONFIG_NOT_FOUND"
    (tmp_path / "config.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ValidationError) as malformed:
        load_config()
    assert malformed.value.code == "CONFIG_INVALID"


def test_sensitive_config_is_masked(isolated: dict[str, object]) -> None:
    shown = masked_config(load_config(), 11)
    assert shown["bank"]["accountNumber"].endswith("1234")
    assert "00000000" not in shown["bank"]["accountNumber"]
    assert shown["bank"]["signaturePath"] == "[configured]"


def test_doctor_reports_missing_signature(isolated: dict[str, object]) -> None:
    Path(isolated["config_home"], "signature.png").unlink()
    result = run_doctor()
    assert result["ok"] is False
    assert result["checks"]["signature"]["code"] == "SIGNATURE_NOT_FOUND"


def test_json_success_has_no_decorative_stdout(isolated: dict[str, object], capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["draft", "--month", "2026-09", "--json"]) == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["ok"] is True
    assert parsed["draftId"]
    assert captured.err == ""


def test_json_error_is_parseable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("TECOLOTE_CONFIG_HOME", str(tmp_path / "missing"))
    assert main(["config", "show", "--json"]) == 2
    parsed = json.loads(capsys.readouterr().out)
    assert parsed == {
        "ok": False,
        "error": {
            "code": "CONFIG_NOT_FOUND",
            "message": f"Configuration not found at {tmp_path / 'missing' / 'config.json'}. Run 'tecolote config init'.",
        },
    }


def test_json_help_is_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--help", "--json"]) == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["ok"] is True
    assert "tecolote" in parsed["help"]


def test_json_config_init_never_prompts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TECOLOTE_CONFIG_HOME", str(tmp_path / "config"))
    assert main(["config", "init", "--json"]) == 2
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["error"]["code"] == "CLI_USAGE_ERROR"


def test_renderer_creates_a_pdf(isolated: dict[str, object], tmp_path: Path) -> None:
    config = load_config()
    draft = create_draft(config, "2026-09", 11, [])
    destination = tmp_path / "rendered.pdf"
    render_invoice(destination, draft["invoices"][0], config)
    assert destination.read_bytes().startswith(b"%PDF")
    assert destination.stat().st_size > 1000
