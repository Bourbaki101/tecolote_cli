from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .drafts import delete_draft, load_draft
from .errors import FilesystemError, RenderError, ValidationError
from .renderer import render_invoice
from .state import StateLock, load_state, save_state


Renderer = Callable[[Path, dict[str, Any], dict[str, Any]], None]


def commit_draft(draft_id: str, renderer: Renderer = render_invoice) -> dict[str, Any]:
    # Validate existence before taking the global state lock, then reload under
    # the lock so the committed bytes still come from a protected snapshot.
    load_draft(draft_id)
    with StateLock():
        draft = load_draft(draft_id)
        config = draft["configSnapshot"]
        state = load_state(int(config["invoice"]["initialNextNumber"]))
        expected = int(draft["expectedNextInvoiceNumber"])
        actual = int(state["nextInvoiceNumber"])
        if actual != expected:
            raise ValidationError(
                "DRAFT_CONFLICT",
                "Invoice numbering changed after this draft was created; create a new draft.",
                {"expectedNextInvoiceNumber": expected, "actualNextInvoiceNumber": actual},
            )

        signature = Path(str(config["bank"]["signaturePath"]))
        if not signature.is_file():
            raise ValidationError("SIGNATURE_NOT_FOUND", "Configured signature file does not exist.")

        root = Path(str(config["invoice"]["outputDirectory"]))
        invoices = draft.get("invoices")
        if not isinstance(invoices, list) or not invoices:
            raise ValidationError("DRAFT_INVALID", "Draft contains no invoices.")
        destinations = [root / str(invoice["relativeOutputPath"]) for invoice in invoices]
        for destination in destinations:
            if destination.exists():
                raise ValidationError(
                    "OUTPUT_COLLISION", "An invoice output file already exists.", {"path": str(destination)}
                )

        try:
            root.mkdir(parents=True, exist_ok=True)
            staging = Path(tempfile.mkdtemp(prefix=".tecolote-", dir=root))
        except OSError as exc:
            raise FilesystemError("Could not prepare the output directory.") from exc

        staged: list[Path] = []
        published: list[Path] = []
        try:
            for index, invoice in enumerate(invoices):
                temporary = staging / f"invoice-{index}.pdf"
                renderer(temporary, invoice, config)
                if not temporary.is_file() or temporary.stat().st_size == 0:
                    raise RenderError("PDF renderer did not produce a valid file.")
                staged.append(temporary)

            for destination in destinations:
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    raise ValidationError(
                        "OUTPUT_COLLISION", "An invoice output file already exists.", {"path": str(destination)}
                    )

            # Hard-link publication is atomic and refuses to overwrite a raced-in file.
            for temporary, destination in zip(staged, destinations, strict=True):
                try:
                    os.link(temporary, destination)
                except FileExistsError as exc:
                    raise ValidationError(
                        "OUTPUT_COLLISION", "An invoice output file already exists.", {"path": str(destination)}
                    ) from exc
                published.append(destination)

            generated_at = datetime.now(timezone.utc).isoformat()
            records = []
            for invoice, destination in zip(invoices, destinations, strict=True):
                records.append(
                    {
                        "invoiceNumber": int(invoice["invoiceNumber"]),
                        "month": str(invoice["month"]),
                        "period": str(invoice["period"]),
                        "generatedAt": generated_at,
                        "totalCents": int(invoice["totalCents"]),
                        "outputPath": str(destination),
                        "draftId": draft_id,
                    }
                )
            new_state = {
                **state,
                "nextInvoiceNumber": expected + len(invoices),
                "history": [*state["history"], *records],
            }
            save_state(new_state)
        except (ValidationError, RenderError, FilesystemError):
            for destination in published:
                try:
                    destination.unlink(missing_ok=True)
                except OSError:
                    pass
            raise
        except OSError as exc:
            for destination in published:
                try:
                    destination.unlink(missing_ok=True)
                except OSError:
                    pass
            raise FilesystemError("Could not publish generated invoice files.") from exc
        finally:
            shutil.rmtree(staging, ignore_errors=True)

        try:
            delete_draft(draft_id)
        except FilesystemError:
            pass
        return {
            "ok": True,
            "draftId": draft_id,
            "invoices": [
                {
                    "invoiceNumber": record["invoiceNumber"],
                    "totalCents": record["totalCents"],
                    "outputPath": record["outputPath"],
                }
                for record in records
            ],
            "nextInvoiceNumber": new_state["nextInvoiceNumber"],
        }
