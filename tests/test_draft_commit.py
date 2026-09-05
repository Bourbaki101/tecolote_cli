from __future__ import annotations

from pathlib import Path

import pytest

from tecolote.config import load_config
from tecolote.drafts import create_draft
from tecolote.errors import RenderError, ValidationError
from tecolote.service import commit_draft
from tecolote.state import load_state, save_state, state_path


def fake_renderer(path: Path, invoice: dict[str, object], config: dict[str, object]) -> None:
    path.write_bytes(b"%PDF-1.4\n% test\n")


def test_draft_does_not_increment_or_create_history(isolated: dict[str, object]) -> None:
    config = load_config()
    draft = create_draft(config, "2026-09", 11, [])
    assert draft["expectedNextInvoiceNumber"] == 11
    assert not state_path().exists()
    state = load_state(11)
    assert state["nextInvoiceNumber"] == 11
    assert state["history"] == []


def test_commit_generates_history_and_increments(isolated: dict[str, object]) -> None:
    config = load_config()
    draft = create_draft(config, "2026-09", 11, [])
    result = commit_draft(draft["draftId"], renderer=fake_renderer)
    assert result["nextInvoiceNumber"] == 12
    assert len(result["invoices"]) == 1
    output = Path(result["invoices"][0]["outputPath"])
    assert output.read_bytes().startswith(b"%PDF")
    state = load_state(11)
    assert state["nextInvoiceNumber"] == 12
    assert state["history"][0]["draftId"] == draft["draftId"]


def test_missing_draft_fails() -> None:
    with pytest.raises(ValidationError) as caught:
        commit_draft("0000000000000000", renderer=fake_renderer)
    assert caught.value.code == "DRAFT_NOT_FOUND"


def test_numbering_conflict_fails_safely(isolated: dict[str, object]) -> None:
    config = load_config()
    draft = create_draft(config, "2026-09", 11, [])
    save_state({"version": 1, "nextInvoiceNumber": 12, "history": []})
    with pytest.raises(ValidationError) as caught:
        commit_draft(draft["draftId"], renderer=fake_renderer)
    assert caught.value.code == "DRAFT_CONFLICT"
    assert not list(Path(isolated["output"]).rglob("*.pdf"))


def test_collision_does_not_overwrite(isolated: dict[str, object]) -> None:
    config = load_config()
    draft = create_draft(config, "2026-09", 11, [])
    destination = Path(isolated["output"]) / draft["invoices"][0]["relativeOutputPath"]
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"keep")
    with pytest.raises(ValidationError) as caught:
        commit_draft(draft["draftId"], renderer=fake_renderer)
    assert caught.value.code == "OUTPUT_COLLISION"
    assert destination.read_bytes() == b"keep"
    assert load_state(11)["nextInvoiceNumber"] == 11


def test_failed_renderer_does_not_consume_number(isolated: dict[str, object]) -> None:
    config = load_config()
    draft = create_draft(config, "2026-09", 11, [])

    def fail(path: Path, invoice: dict[str, object], snapshot: dict[str, object]) -> None:
        raise RenderError("expected test failure")

    with pytest.raises(RenderError):
        commit_draft(draft["draftId"], renderer=fail)
    assert load_state(11)["nextInvoiceNumber"] == 11
    assert load_state(11)["history"] == []
    assert not list(Path(isolated["output"]).rglob("*.pdf"))


def test_missing_signature_fails_with_specific_code(isolated: dict[str, object]) -> None:
    config = load_config()
    draft = create_draft(config, "2026-09", 11, [])
    Path(config["bank"]["signaturePath"]).unlink()
    with pytest.raises(ValidationError) as caught:
        commit_draft(draft["draftId"], renderer=fake_renderer)
    assert caught.value.code == "SIGNATURE_NOT_FOUND"
    assert load_state(11)["nextInvoiceNumber"] == 11
