from __future__ import annotations

import json
import os
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from .config import write_json_secure
from .errors import FilesystemError, ValidationError
from .paths import state_dir


def state_path() -> Path:
    return state_dir() / "state.json"


def drafts_dir() -> Path:
    return state_dir() / "drafts"


def load_state(initial_next_number: int) -> dict[str, Any]:
    path = state_path()
    if not path.exists():
        return {"version": 1, "nextInvoiceNumber": initial_next_number, "history": []}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError("STATE_INVALID", "Persistent state is not valid JSON.") from exc
    except OSError as exc:
        raise FilesystemError("Could not read persistent state.") from exc
    if (
        not isinstance(raw, dict)
        or raw.get("version") != 1
        or not isinstance(raw.get("nextInvoiceNumber"), int)
        or raw["nextInvoiceNumber"] < 1
        or not isinstance(raw.get("history"), list)
    ):
        raise ValidationError("STATE_INVALID", "Persistent state has an invalid schema.")
    return raw


def save_state(state: dict[str, Any]) -> None:
    write_json_secure(state_path(), state)


class StateLock(AbstractContextManager["StateLock"]):
    def __init__(self) -> None:
        self.path = state_dir() / "state.lock"
        self.handle: Any = None

    def __enter__(self) -> "StateLock":
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            self.handle = self.path.open("a+b")
            try:
                self.path.chmod(0o600)
            except OSError:
                pass
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                if self.handle.tell() == 0:
                    self.handle.write(b"0")
                    self.handle.flush()
                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self
        except (OSError, BlockingIOError) as exc:
            if self.handle:
                self.handle.close()
            raise ValidationError("STATE_LOCKED", "Another Tecolote operation is in progress.") from exc

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        if not self.handle:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self.handle.seek(0)
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
