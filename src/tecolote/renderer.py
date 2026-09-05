from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from .errors import RenderError
from .money import format_money


DARK = (0.22, 0.22, 0.22)


def renderer_available() -> bool:
    try:
        import reportlab  # noqa: F401

        return True
    except ImportError:
        return False


def _wrap(text: str, font: str, size: float, width: float) -> list[str]:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and stringWidth(candidate, font, size) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [""]


def _draw_text_lines(
    pdf: Any, text: str, x: float, y: float, width: float, font: str, size: float, leading: float
) -> float:
    for line in _wrap(text, font, size, width):
        pdf.drawString(x, y, line)
        y -= leading
    return y


def _draw_item(pdf: Any, line: dict[str, Any], y: float, currency: str) -> float:
    from reportlab.pdfbase.pdfmetrics import stringWidth

    font = "Helvetica-Bold"
    size = 10.5
    description_width = 285 if line.get("kind") == "service" else 345
    description_lines = _wrap(str(line["description"]), font, size, description_width)
    amount = format_money(int(line["amountCents"]), currency)
    pdf.setFont(font, size)
    for index, description_line in enumerate(description_lines):
        pdf.drawString(71, y, description_line)
        if index == len(description_lines) - 1:
            end = 71 + stringWidth(description_line, font, size) + 2
            amount_left = 505 - stringWidth(amount, font, size)
            dot_width = stringWidth(".", font, size)
            dots = max(2, int((amount_left - end - 4) / dot_width))
            pdf.drawString(end, y, "." * dots)
            pdf.drawRightString(505, y, amount)
        y -= 15
    return y - 14


def render_invoice(path: Path, invoice: dict[str, Any], config: dict[str, Any]) -> None:
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas

        lines = invoice.get("lines", [])
        required_height = sum(29 + (15 if len(str(line["description"])) > 55 else 0) for line in lines)
        if required_height > 205:
            raise RenderError("Invoice has too many line items to fit the one-page reference layout.")

        path.parent.mkdir(parents=True, exist_ok=True)
        pdf = canvas.Canvas(str(path), pagesize=A4, pageCompression=1)
        pdf.setTitle(f"Invoice {invoice['invoiceNumber']}")
        pdf.setAuthor(str(config["user"]["fullName"]))
        pdf.setCreator("Tecolote CLI")
        pdf.setFillColorRGB(*DARK)
        pdf.setStrokeColorRGB(*DARK)

        # Reference-matched masthead.
        pdf.setLineWidth(0.65)
        pdf.line(70, 738, 315, 738)
        title = pdf.beginText(336, 754)
        title.setFont("Helvetica", 30)
        title.setCharSpace(7.4)
        title.textLine("SERVICE")
        title.setLeading(52)
        title.textLine("INVOICE")
        title.setCharSpace(0)
        pdf.drawText(title)

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica-Bold", 10.5)
        pdf.drawString(64, 650, "ISSUED TO:")
        pdf.drawString(64, 637, str(config["client"]["companyName"]))
        pdf.setFont("Helvetica", 10.5)
        _draw_text_lines(
            pdf, str(config["client"]["companyAddress"]), 64, 624, 250, "Helvetica", 10.5, 12
        )

        issued = date.fromisoformat(str(invoice["issueDate"]))
        pdf.setFillColorRGB(*DARK)
        pdf.setFont("Helvetica-Bold", 10.5)
        pdf.drawString(373, 650, "INVOICE NO:")
        pdf.drawString(373, 633, "DATE:")
        pdf.drawString(461, 650, str(invoice["invoiceNumber"]))
        pdf.drawString(461, 633, issued.strftime("%d/%m/%Y"))

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(77, 581, "DESCRIPTION")
        pdf.drawRightString(513, 581, "AMOUNT")
        pdf.setLineWidth(0.55)
        pdf.line(70, 567, 526, 567)

        currency = str(config["compensation"]["currency"])
        y = 542.0
        for item in lines:
            y = _draw_item(pdf, item, y, currency)

        totals_top = min(y + 2, 372)
        if totals_top < 320:
            raise RenderError("Invoice line items overlap the totals section.")
        pdf.setStrokeColorRGB(*DARK)
        pdf.line(70, totals_top, 526, totals_top)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(82, totals_top - 22, "SUBTOTAL")
        pdf.drawRightString(507, totals_top - 22, format_money(int(invoice["subtotalCents"]), currency))
        pdf.setFont("Helvetica", 10.5)
        pdf.drawString(295, totals_top - 41, "Tax")
        pdf.drawRightString(518, totals_top - 41, "0 %")
        pdf.setFont("Helvetica-Bold", 11.5)
        pdf.drawString(295, totals_top - 59, "TOTAL")
        pdf.drawRightString(508, totals_top - 59, format_money(int(invoice["totalCents"]), currency))

        # Payment details and signature footer.
        pdf.setLineWidth(1.8)
        pdf.rect(63, 79, 252, 122, stroke=1, fill=0)
        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(70, 187, "PAY TO:")
        pdf.setFont("Helvetica", 10.2)
        payment_lines = [
            str(config["bank"]["bank"]),
            str(config["bank"]["bankAddress"]),
            f"Account Name: {config['bank']['accountName']}",
            f"Swift: {config['bank']['swift']}",
            f"Account No.: {config['bank']['accountNumber']}",
        ]
        payment_y = 174.0
        for payment_line in payment_lines:
            payment_y = _draw_text_lines(pdf, payment_line, 70, payment_y, 236, "Helvetica", 10.2, 12)

        pdf.setFont("Helvetica-Bold", 11.5)
        pdf.drawCentredString(438, 188, str(config["user"]["fullName"]))
        signature_path = Path(str(config["bank"]["signaturePath"]))
        if not signature_path.is_file():
            raise RenderError("Configured signature file does not exist.")
        image = ImageReader(str(signature_path))
        image_width, image_height = image.getSize()
        max_width, max_height = 110.0, 66.0
        scale = min(max_width / image_width, max_height / image_height)
        draw_width, draw_height = image_width * scale, image_height * scale
        pdf.drawImage(
            image,
            438 - draw_width / 2,
            111,
            width=draw_width,
            height=draw_height,
            preserveAspectRatio=True,
            mask="auto",
        )

        pdf.showPage()
        pdf.save()
    except RenderError:
        path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        path.unlink(missing_ok=True)
        raise RenderError("PDF generation failed.") from exc
