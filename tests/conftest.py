from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from tecolote.config import write_json_secure


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> dict[str, object]:
    config_home = tmp_path / "config"
    state_home = tmp_path / "state"
    output = tmp_path / "invoices"
    signature = config_home / "signature.png"
    signature.parent.mkdir(parents=True)
    Image.new("RGBA", (32, 16), (0, 0, 0, 128)).save(signature)
    monkeypatch.setenv("TECOLOTE_CONFIG_HOME", str(config_home))
    monkeypatch.setenv("TECOLOTE_STATE_HOME", str(state_home))
    raw = {
        "version": 1,
        "user": {"fullName": "Example Contractor"},
        "bank": {
            "bank": "Example Bank",
            "bankAddress": "100 Example Street, Example City",
            "accountName": "Example Contractor",
            "swift": "EXAMPLE1A",
            "accountNumber": "000000001234",
            "signaturePath": str(signature),
        },
        "compensation": {"monthlyCents": 217000, "currency": "USD", "schedule": "monthly"},
        "client": {"companyName": "Example Client Ltd.", "companyAddress": "Example City, Example Country"},
        "invoice": {"initialNextNumber": 11, "outputDirectory": str(output)},
    }
    write_json_secure(config_home / "config.json", raw)
    return {"config": raw, "config_home": config_home, "state_home": state_home, "output": output}
