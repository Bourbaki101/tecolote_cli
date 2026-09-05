from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TecoloteError(Exception):
    code: str
    message: str
    exit_code: int = 2
    details: dict[str, object] | None = None

    def __str__(self) -> str:
        return self.message


class ValidationError(TecoloteError):
    def __init__(self, code: str, message: str, details: dict[str, object] | None = None):
        super().__init__(code, message, 2, details)


class RenderError(TecoloteError):
    def __init__(self, message: str, details: dict[str, object] | None = None):
        super().__init__("PDF_RENDER_FAILED", message, 3, details)


class FilesystemError(TecoloteError):
    def __init__(self, message: str, details: dict[str, object] | None = None):
        super().__init__("FILESYSTEM_ERROR", message, 4, details)
