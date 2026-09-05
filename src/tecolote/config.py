from __future__ import annotations

import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from .errors import FilesystemError, ValidationError
from .paths import config_path, default_output_dir


REQUIRED_TEXT_FIELDS = (
    ("user", "fullName"),
    ("bank", "bank"),
    ("bank", "bankAddress"),
    ("bank", "accountName"),
    ("bank", "swift"),
    ("bank", "accountNumber"),
    ("bank", "signaturePath"),
    ("client", "companyName"),
    ("client", "companyAddress"),
    ("compensation", "currency"),
    ("invoice", "outputDirectory"),
)


def _secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def write_json_secure(path: Path, data: dict[str, Any]) -> None:
    try:
        _secure_dir(path.parent)
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temp_name, 0o600)
            os.replace(temp_name, path)
            try:
                path.chmod(0o600)
            except OSError:
                pass
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
    except OSError as exc:
        raise FilesystemError(f"Could not write {path}.") from exc


def validate_config(raw: object, source: Path | None = None) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValidationError("CONFIG_INVALID", "Configuration root must be a JSON object.")
    config = deepcopy(raw)
    if config.get("version") != 1:
        raise ValidationError("CONFIG_INVALID", "Configuration version must be 1.")
    for section, field in REQUIRED_TEXT_FIELDS:
        section_value = config.get(section)
        if not isinstance(section_value, dict):
            raise ValidationError("CONFIG_INVALID", f"Missing configuration section: {section}.")
        value = section_value.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError("CONFIG_INVALID", f"Missing required configuration field: {section}.{field}.")
        section_value[field] = value.strip()

    compensation = config.get("compensation", {})
    monthly_cents = compensation.get("monthlyCents")
    if not isinstance(monthly_cents, int) or isinstance(monthly_cents, bool) or monthly_cents <= 0:
        raise ValidationError("CONFIG_INVALID", "compensation.monthlyCents must be a positive integer.")
    if monthly_cents % 2:
        raise ValidationError(
            "CONFIG_INVALID", "compensation.monthlyCents must be even so both half-month amounts are equal."
        )
    currency = compensation["currency"]
    if len(currency) != 3 or not currency.isalpha():
        raise ValidationError("CONFIG_INVALID", "compensation.currency must be a three-letter code.")
    compensation["currency"] = currency.upper()
    if compensation.get("schedule") not in {"monthly", "twice-monthly"}:
        raise ValidationError("CONFIG_INVALID", "compensation.schedule must be monthly or twice-monthly.")

    invoice = config.get("invoice", {})
    initial = invoice.get("initialNextNumber")
    if not isinstance(initial, int) or isinstance(initial, bool) or initial < 1:
        raise ValidationError("CONFIG_INVALID", "invoice.initialNextNumber must be a positive integer.")

    base = source.parent if source else Path.cwd()
    signature = Path(config["bank"]["signaturePath"]).expanduser()
    output = Path(config["invoice"]["outputDirectory"]).expanduser()
    config["bank"]["signaturePath"] = str((base / signature).resolve() if not signature.is_absolute() else signature)
    config["invoice"]["outputDirectory"] = str((base / output).resolve() if not output.is_absolute() else output)
    return config


def load_config(path: Path | None = None) -> dict[str, Any]:
    target = path or config_path()
    if not target.exists():
        raise ValidationError(
            "CONFIG_NOT_FOUND", f"Configuration not found at {target}. Run 'tecolote config init'."
        )
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValidationError("CONFIG_INVALID", f"Configuration is not valid JSON (line {exc.lineno}).") from exc
    except OSError as exc:
        raise FilesystemError(f"Could not read configuration at {target}.") from exc
    return validate_config(raw, target)


def masked_config(config: dict[str, Any], current_next_number: int | None = None) -> dict[str, Any]:
    result = deepcopy(config)
    account = result["bank"]["accountNumber"]
    result["bank"]["accountNumber"] = "*" * max(8, len(account) - 4) + account[-4:]
    result["bank"]["signaturePath"] = "[configured]"
    if current_next_number is not None:
        result["invoice"]["nextNumber"] = current_next_number
    return result


def default_template() -> dict[str, Any]:
    return {
        "version": 1,
        "user": {"fullName": "Example Contractor"},
        "bank": {
            "bank": "Example Bank",
            "bankAddress": "100 Example Street, Example City",
            "accountName": "Example Contractor",
            "swift": "EXAMPLE1A",
            "accountNumber": "000000001234",
            "signaturePath": str((config_path().parent / "signature.png").resolve()),
        },
        "compensation": {"monthlyCents": 200000, "currency": "USD", "schedule": "monthly"},
        "client": {"companyName": "Example Client Ltd.", "companyAddress": "Example City, Example Country"},
        "invoice": {"initialNextNumber": 1, "outputDirectory": str(default_output_dir())},
    }
