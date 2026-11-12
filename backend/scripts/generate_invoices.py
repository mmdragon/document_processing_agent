"""Generate the synthetic invoice dataset and its ground-truth JSON.

Every vendor, customer, address, and number here is fictional. Each PDF carries a
"SYNTHETIC" banner and PDF metadata saying so.

Usage (from backend/):
    uv run python scripts/generate_invoices.py

Outputs:
    sample_data/invoices/<id>.pdf
    sample_data/ground_truth/<id>.json
"""

from __future__ import annotations

import io
import json
import random
import sys
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pymupdf
from PIL import Image, ImageFilter
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.ground_truth import GroundTruth  # noqa: E402

OUT_PDF = BACKEND_ROOT / "sample_data" / "invoices"
OUT_GT = BACKEND_ROOT / "sample_data" / "ground_truth"

SYNTHETIC_BANNER = "SYNTHETIC SAMPLE - FICTIONAL DATA - NOT A REAL INVOICE"
SYNTHETIC_FOOTER = (
    "Synthetic document generated for software testing. "
    "All names, addresses and numbers are fictional."
)
CUSTOMER = ["Bluepine Robotics LLC (fictional)", "88 Orchard Loop", "Maplebrook, CA 94000"]
CENT = Decimal("0.01")


def D(value: str | int) -> Decimal:
    return Decimal(str(value))


def money_round(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


# --------------------------------------------------------------------------- specs


@dataclass
class Item:
    description: str
    quantity: Decimal
    unit_price: Decimal
    printed_amount: Decimal | None = None  # set to print a wrong line amount

    @property
    def amount(self) -> Decimal:
        if self.printed_amount is not None:
            return self.printed_amount
        return money_round(self.quantity * self.unit_price)


@dataclass
class InvoiceSpec:
    doc_id: str
    scenario: str
    description: str
    vendor_name: str
    vendor_address: list[str]
    invoice_number: str | None
    invoice_date: date | None
    invoice_date_raw: str | None
    due_date: date | None
    due_date_raw: str | None
    items: list[Item]
    currency: str = "USD"
    po_number: str | None = None
    payment_terms: str | None = None
    discount_rate: Decimal | None = None
    tax_rate: Decimal | None = None
    tax_label: str = "Sales tax"
    shipping: Decimal | None = None
    printed_total: Decimal | None = None  # set to print a wrong total
    render_mode: str = "text"
    expected_issues: list[str] = field(default_factory=list)
    duplicate_of: str | None = None

    # Totals as printed on the document.
    @property
    def subtotal(self) -> Decimal:
        return sum((i.amount for i in self.items), Decimal("0.00"))

    @property
    def discount(self) -> Decimal | None:
        if self.discount_rate is None:
            return None
        return money_round(self.subtotal * self.discount_rate / 100)

    @property
    def tax(self) -> Decimal | None:
        if self.tax_rate is None:
            return None
        return money_round((self.subtotal - (self.discount or 0)) * self.tax_rate / 100)

    @property
    def total(self) -> Decimal:
        if self.printed_total is not None:
            return self.printed_total
        return self.subtotal - (self.discount or 0) + (self.tax or 0) + (self.shipping or 0)


# --------------------------------------------------------------------------- formatting


def fmt_number(value: Decimal, currency: str) -> str:
    s = f"{value:,.2f}"
    if currency == "EUR":  # European grouping: 1.234,56
        s = s.replace(",", "_").replace(".", ",").replace("_", ".")
    return s


def fmt_money(value: Decimal, currency: str) -> str:
    n = fmt_number(value, currency)
    return {"USD": f"${n}", "EUR": f"{n} €"}.get(currency, f"{n} {currency}")


def fmt_qty(q: Decimal, currency: str) -> str:
    s = format(q.normalize(), "f")
    return s.replace(".", ",") if currency == "EUR" else s


def fmt_rate(rate: Decimal) -> str:
    return format(rate.normalize(), "f")


# --------------------------------------------------------------------------- rendering


def render_text_pdf(spec: InvoiceSpec) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER, invariant=1)
    c.setTitle(f"SYNTHETIC invoice {spec.doc_id}")
    c.setSubject("Synthetic test document - fictional data")
    c.setAuthor("document-processing-agent sample generator")
    width, height = LETTER
    left, right = 54, width - 54
    cur = spec.currency

    # Synthetic banner
    c.setFillGray(0.88)
    c.rect(0, height - 28, width, 28, stroke=0, fill=1)
    c.setFillGray(0.2)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(width / 2, height - 18, SYNTHETIC_BANNER)
    c.setFillGray(0)

    # Vendor block
    y = height - 70
    c.setFont("Helvetica-Bold", 16)
    c.drawString(left, y, spec.vendor_name)
    c.setFont("Helvetica", 10)
    for line in spec.vendor_address:
        y -= 14
        c.drawString(left, y, line)

    # Invoice meta block (only rows that are present on the document)
    c.setFont("Helvetica-Bold", 20)
    c.drawRightString(right, height - 70, "INVOICE")
    meta = [
        ("Invoice No.", spec.invoice_number),
        ("Invoice Date", spec.invoice_date_raw),
        ("Due Date", spec.due_date_raw),
        ("PO Number", spec.po_number),
        ("Terms", spec.payment_terms),
    ]
    my = height - 92
    for label, value in meta:
        if value is None:
            continue
        c.setFont("Helvetica-Bold", 10)
        c.drawRightString(right - 150, my, f"{label}:")
        c.setFont("Helvetica", 10)
        c.drawString(right - 144, my, value)
        my -= 14

    # Bill-to
    y = min(y, my) - 30
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y, "Bill To:")
    c.setFont("Helvetica", 10)
    for line in CUSTOMER:
        y -= 14
        c.drawString(left, y, line)

    # Line item table
    y -= 32
    cols = {"desc": left, "qty": 360, "unit": 450, "amount": right}
    c.setFillGray(0.93)
    c.rect(left - 4, y - 5, right - left + 8, 18, stroke=0, fill=1)
    c.setFillGray(0)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(cols["desc"], y, "Description")
    c.drawRightString(cols["qty"], y, "Qty")
    c.drawRightString(cols["unit"], y, "Unit Price")
    c.drawRightString(cols["amount"], y, "Amount")
    c.setFont("Helvetica", 10)
    for item in spec.items:
        y -= 18
        c.drawString(cols["desc"], y, item.description)
        c.drawRightString(cols["qty"], y, fmt_qty(item.quantity, cur))
        c.drawRightString(cols["unit"], y, fmt_money(item.unit_price, cur))
        c.drawRightString(cols["amount"], y, fmt_money(item.amount, cur))
    y -= 10
    c.line(left, y, right, y)

    # Totals
    rows: list[tuple[str, Decimal, bool]] = [("Subtotal", spec.subtotal, False)]
    if spec.discount is not None:
        rows.append((f"Discount ({fmt_rate(spec.discount_rate)}%)", -spec.discount, False))
    if spec.tax is not None:
        rows.append((f"{spec.tax_label} ({fmt_rate(spec.tax_rate)}%)", spec.tax, False))
    if spec.shipping is not None:
        rows.append(("Shipping", spec.shipping, False))
    rows.append((f"Total ({cur})", spec.total, True))
    for label, value, bold in rows:
        y -= 18
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 11 if bold else 10)
        c.drawRightString(cols["unit"], y, label)
        sign = "-" if value < 0 else ""
        c.drawRightString(cols["amount"], y, sign + fmt_money(abs(value), cur))

    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.setFillGray(0.35)
    c.drawCentredString(width / 2, 30, SYNTHETIC_FOOTER)
    c.showPage()
    c.save()
    return buf.getvalue()


def rasterize(pdf_bytes: bytes, *, low_quality: bool, seed: int) -> bytes:
    """Turn a text PDF into an image-only PDF (no text layer), like a scan."""
    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page = src[0]
    pix = page.get_pixmap(dpi=100 if low_quality else 200, colorspace=pymupdf.csGRAY)
    img = Image.frombytes("L", (pix.width, pix.height), pix.samples)

    if low_quality:
        rng = random.Random(seed)
        img = img.rotate(1.4, resample=Image.Resampling.BICUBIC, fillcolor=255)
        img = img.filter(ImageFilter.GaussianBlur(0.9))
        # Seeded Gaussian noise (Image.effect_noise is not reproducible).
        noise = Image.frombytes(
            "L",
            img.size,
            bytes(max(0, min(255, int(rng.gauss(128, 40)))) for _ in range(img.width * img.height)),
        )
        img = Image.blend(img, noise, 0.18)
        # Speckles, like dust on a scanner glass.
        px = img.load()
        for _ in range(img.width * img.height // 400):
            px[rng.randrange(img.width), rng.randrange(img.height)] = rng.choice((0, 80, 255))
        quality = 22
    else:
        img = img.point(lambda v: min(255, v + 12))  # slightly washed-out paper
        quality = 80

    jpeg = io.BytesIO()
    img.save(jpeg, format="JPEG", quality=quality)

    out = pymupdf.open()
    new_page = out.new_page(width=page.rect.width, height=page.rect.height)
    new_page.insert_image(new_page.rect, stream=jpeg.getvalue())
    out.set_metadata(
        {
            "title": "SYNTHETIC scanned invoice - fictional data",
            "subject": "Synthetic test document - fictional data",
            "author": "document-processing-agent sample generator",
            "creationDate": "",
            "modDate": "",
        }
    )
    return out.tobytes(garbage=4, deflate=True, no_new_id=True)


# --------------------------------------------------------------------------- dataset


def build_specs() -> list[InvoiceSpec]:
    quill_addr = ["1200 Fernhollow Ave, Suite 4", "Springhaven, OR 97000"]
    quill_items = [
        Item("Copy paper, letter (case of 10 reams)", D(10), D("42.50")),
        Item("Gel pens, black (box of 12)", D(6), D("12.75")),
        Item("Desk organizer, bamboo", D(3), D("28.00")),
    ]
    return [
        InvoiceSpec(
            doc_id="inv01_normal",
            scenario="normal",
            description="Normal invoice with correct line items, tax and total.",
            vendor_name="Quillfeather Office Goods",
            vendor_address=quill_addr,
            invoice_number="QOG-2026-0142",
            invoice_date=date(2026, 3, 2),
            invoice_date_raw="March 2, 2026",
            due_date=date(2026, 4, 1),
            due_date_raw="April 1, 2026",
            po_number="PO-55120",
            payment_terms="Net 30",
            items=quill_items,
            tax_rate=D("8.25"),
        ),
        InvoiceSpec(
            doc_id="inv02_missing_invoice_number",
            scenario="missing_invoice_number",
            description="No invoice number is printed anywhere on the document.",
            vendor_name="Pinecrest Print Works",
            vendor_address=["77 Ledger Street", "Cedar Falls, WA 98000"],
            invoice_number=None,
            invoice_date=date(2026, 3, 9),
            invoice_date_raw="March 9, 2026",
            due_date=date(2026, 3, 24),
            due_date_raw="March 24, 2026",
            payment_terms="Net 15",
            items=[
                Item("Business cards (box of 500)", D(4), D("38.00")),
                Item("Tri-fold brochures (pack of 250)", D(2), D("115.00")),
            ],
            expected_issues=["missing_invoice_number"],
        ),
        InvoiceSpec(
            doc_id="inv03_missing_due_date",
            scenario="missing_due_date",
            description=(
                "No due date is printed. Terms say Net 30, but the due date must not be "
                "inferred silently."
            ),
            vendor_name="Mossgate Facilities Services",
            vendor_address=["9 Quarry Row", "Elmstead, CO 80000"],
            invoice_number="MFS-88213",
            invoice_date=date(2026, 3, 12),
            invoice_date_raw="March 12, 2026",
            due_date=None,
            due_date_raw=None,
            payment_terms="Net 30",
            items=[
                Item("HVAC quarterly maintenance", D(1), D("640.00")),
                Item("Air filter replacement 20x25x1", D(12), D("9.50")),
            ],
            expected_issues=["missing_due_date"],
        ),
        InvoiceSpec(
            doc_id="inv04_arithmetic_mismatch",
            scenario="arithmetic_mismatch",
            description="Printed total (763.70) does not equal the subtotal (736.70).",
            vendor_name="Harbor Lantern Logistics",
            vendor_address=["410 Wharfside Drive", "Port Calder, ME 04000"],
            invoice_number="HLL-30917",
            invoice_date=date(2026, 2, 20),
            invoice_date_raw="February 20, 2026",
            due_date=date(2026, 3, 22),
            due_date_raw="March 22, 2026",
            payment_terms="Net 30",
            items=[
                Item("Pallet freight - zone 3", D(2), D("310.00")),
                Item("Liftgate service", D(1), D("75.00")),
                Item("Fuel surcharge", D(1), D("41.70")),
            ],
            printed_total=D("763.70"),
            expected_issues=["total_mismatch"],
        ),
        InvoiceSpec(
            doc_id="inv05_duplicate",
            scenario="duplicate",
            description=(
                "Same vendor and invoice number as inv01_normal, re-sent with a later "
                "date. Should be flagged as a POSSIBLE duplicate only."
            ),
            vendor_name="Quillfeather Office Goods",
            vendor_address=quill_addr,
            invoice_number="QOG-2026-0142",
            invoice_date=date(2026, 3, 16),
            invoice_date_raw="March 16, 2026",
            due_date=date(2026, 4, 15),
            due_date_raw="April 15, 2026",
            po_number="PO-55120",
            payment_terms="Net 30",
            items=quill_items,
            tax_rate=D("8.25"),
            expected_issues=["possible_duplicate"],
            duplicate_of="inv01_normal",
        ),
        InvoiceSpec(
            doc_id="inv06_multiple_line_items",
            scenario="multiple_line_items",
            description="Nine line items including a fractional quantity (labor hours).",
            vendor_name="Lumenvale Electrical Supply",
            vendor_address=["3301 Copperline Blvd", "Brightwater, TX 75000"],
            invoice_number="LES-4471-B",
            invoice_date=date(2026, 3, 5),
            invoice_date_raw="March 5, 2026",
            due_date=date(2026, 4, 4),
            due_date_raw="April 4, 2026",
            po_number="BR-2026-118",
            payment_terms="Net 30",
            items=[
                Item("LED panel 2x4 ft, 40W", D(24), D("54.90")),
                Item("THHN wire 12 AWG, 500 ft spool", D(3), D("89.00")),
                Item("Duplex receptacle 20A", D(40), D("2.35")),
                Item("Single-pole switch", D(30), D("1.98")),
                Item("Junction box 4 in", D(25), D("3.10")),
                Item("Wire nuts (bag of 100)", D(5), D("6.45")),
                Item("EMT conduit 1/2 in x 10 ft", D(18), D("7.80")),
                Item("Breaker 20A single pole", D(12), D("11.25")),
                Item("Labor - fixture install (hours)", D("6.5"), D("85.00")),
            ],
            tax_rate=D("7"),
        ),
        InvoiceSpec(
            doc_id="inv07_discount",
            scenario="discount",
            description="10% discount applied to the subtotal before the total.",
            vendor_name="Cobaltfern Software Studio",
            vendor_address=["15 Lattice Lane, Floor 2", "Riverbend, MN 55000"],
            invoice_number="CSS-2026-007",
            invoice_date=date(2026, 1, 28),
            invoice_date_raw="January 28, 2026",
            due_date=date(2026, 2, 27),
            due_date_raw="February 27, 2026",
            payment_terms="Net 30",
            items=[
                Item("Annual design tool licence (per seat)", D(5), D("240.00")),
                Item("Onboarding workshop", D(1), D("450.00")),
            ],
            discount_rate=D("10"),
        ),
        InvoiceSpec(
            doc_id="inv08_tax_and_shipping",
            scenario="tax_and_shipping",
            description="Sales tax on the subtotal plus an untaxed shipping charge.",
            vendor_name="Ironbark Industrial Parts",
            vendor_address=["600 Foundry Road", "Millhaven, OH 43000"],
            invoice_number="IIP-77310",
            invoice_date=date(2026, 3, 3),
            invoice_date_raw="March 3, 2026",
            due_date=date(2026, 4, 2),
            due_date_raw="April 2, 2026",
            po_number="PO-88731",
            payment_terms="Net 30",
            items=[
                Item("Hex bolt M10x40 (box of 50)", D(8), D("18.60")),
                Item("Flange nut M10 (box of 100)", D(4), D("14.20")),
                Item("Bearing 6204-2RS", D(20), D("6.75")),
            ],
            tax_rate=D("6.5"),
            shipping=D("35.00"),
        ),
        InvoiceSpec(
            doc_id="inv09_scanned",
            scenario="scanned_image",
            description="Clean image-only PDF (no text layer). Needs OCR.",
            vendor_name="Tidewell Catering Co.",
            vendor_address=["22 Saltgrass Pier", "Bayport, FL 33000"],
            invoice_number="TCC-1189",
            invoice_date=date(2026, 2, 14),
            invoice_date_raw="February 14, 2026",
            due_date=date(2026, 2, 28),
            due_date_raw="February 28, 2026",
            payment_terms="Net 14",
            items=[
                Item("Lunch buffet (per person)", D(35), D("16.50")),
                Item("Coffee service", D(1), D("85.00")),
                Item("Delivery and setup", D(1), D("40.00")),
            ],
            tax_rate=D("9"),
            render_mode="scan",
            expected_issues=["ocr_required"],
        ),
        InvoiceSpec(
            doc_id="inv10_unusual_date_format",
            scenario="unusual_date_format",
            description="Dates written as 'Tuesday, 3rd February 2026' and '2026/03/05'.",
            vendor_name="Glasswing Consulting Group",
            vendor_address=["480 Prism Court", "Hollis Park, NJ 07000"],
            invoice_number="GCG/26/031",
            invoice_date=date(2026, 2, 3),
            invoice_date_raw="Tuesday, 3rd February 2026",
            due_date=date(2026, 3, 5),
            due_date_raw="2026/03/05",
            payment_terms="Net 30",
            items=[
                Item("Process review workshop (days)", D(2), D("1800.00")),
                Item("Travel expenses (pass-through)", D(1), D("412.37")),
            ],
        ),
        InvoiceSpec(
            doc_id="inv11_low_quality_scan",
            scenario="low_quality_ocr",
            description="Blurred, rotated, noisy, low-resolution scan. OCR will be unreliable.",
            vendor_name="Saltmarsh Cleaning Co.",
            vendor_address=["5 Heron Way", "Dunmore Flats, SC 29000"],
            invoice_number="SCC-5502",
            invoice_date=date(2026, 3, 1),
            invoice_date_raw="March 1, 2026",
            due_date=date(2026, 3, 31),
            due_date_raw="March 31, 2026",
            payment_terms="Net 30",
            items=[
                Item("Office deep clean (sq ft)", D(2400), D("0.18")),
                Item("Window cleaning (panes)", D(48), D("3.50")),
            ],
            render_mode="low_quality_scan",
            expected_issues=["ocr_required", "low_quality_scan"],
        ),
        InvoiceSpec(
            doc_id="inv12_non_usd_currency",
            scenario="non_usd_currency",
            description="EUR invoice with European number format (1.825,00) and 20% VAT.",
            vendor_name="Atelier Brume SARL",
            vendor_address=["12 rue des Brumes (fictional)", "69000 Lyon, France"],
            invoice_number="AB-2026-0058",
            invoice_date=date(2026, 1, 15),
            invoice_date_raw="15.01.2026",
            due_date=date(2026, 2, 14),
            due_date_raw="14.02.2026",
            currency="EUR",
            payment_terms="30 days",
            items=[
                Item("Brochure graphic design", D(1), D("1250.00")),
                Item("Printing (500 copies)", D(500), D("1.15")),
            ],
            tax_rate=D("20"),
            tax_label="VAT",
        ),
        InvoiceSpec(
            doc_id="inv13_ambiguous_date",
            scenario="ambiguous_date",
            description=(
                "Invoice date '04/05/2026' could be April 5 or May 4; it must be flagged, "
                "not guessed."
            ),
            vendor_name="Ashgrove Garden Supply",
            vendor_address=["1900 Thornfield Road", "Willow Bend, IL 60000"],
            invoice_number="AGS-6620",
            invoice_date=None,
            invoice_date_raw="04/05/2026",
            due_date=date(2026, 5, 30),
            due_date_raw="May 30, 2026",
            payment_terms="Due by date shown",
            items=[
                Item("Hardwood mulch (cubic yard)", D(6), D("38.00")),
                Item("Cedar planter box", D(2), D("64.99")),
            ],
            expected_issues=["ambiguous_date"],
        ),
        InvoiceSpec(
            doc_id="inv14_line_item_mismatch",
            scenario="line_item_mismatch",
            description=(
                "Line 1 prints 351.00 but 14 x 22.50 = 315.00. Subtotal and total are "
                "consistent with the printed (wrong) line amount."
            ),
            vendor_name="Redkite Courier Services",
            vendor_address=["88 Dispatch Avenue", "Kestrel City, AZ 85000"],
            invoice_number="RCS-90412",
            invoice_date=date(2026, 3, 10),
            invoice_date_raw="March 10, 2026",
            due_date=date(2026, 3, 25),
            due_date_raw="March 25, 2026",
            payment_terms="Net 15",
            items=[
                Item("Same-day courier run", D(14), D("22.50"), printed_amount=D("351.00")),
                Item("Weekend surcharge", D(2), D("15.00")),
            ],
            expected_issues=["line_item_amount_mismatch"],
        ),
    ]


def ground_truth(spec: InvoiceSpec) -> GroundTruth:
    scanned = spec.render_mode != "text"
    return GroundTruth.model_validate(
        {
            "synthetic": True,
            "document_id": spec.doc_id,
            "file_name": f"{spec.doc_id}.pdf",
            "scenario": spec.scenario,
            "description": spec.description,
            "render_mode": spec.render_mode,
            "expected_extraction_method": "ocr" if scanned else "text",
            "expected_issues": spec.expected_issues,
            "duplicate_of": spec.duplicate_of,
            "fields": {
                "vendor_name": spec.vendor_name,
                "vendor_address": ", ".join(spec.vendor_address),
                "invoice_number": spec.invoice_number,
                "invoice_date": spec.invoice_date,
                "invoice_date_raw": spec.invoice_date_raw,
                "due_date": spec.due_date,
                "due_date_raw": spec.due_date_raw,
                "currency": spec.currency,
                "line_items": [
                    {
                        "description": i.description,
                        "quantity": i.quantity,
                        "unit_price": i.unit_price,
                        "amount": i.amount,
                    }
                    for i in spec.items
                ],
                "subtotal": spec.subtotal,
                "discount": spec.discount,
                "tax": spec.tax,
                "shipping": spec.shipping,
                "total": spec.total,
                "purchase_order_number": spec.po_number,
                "payment_terms": spec.payment_terms,
            },
        }
    )


def main() -> None:
    OUT_PDF.mkdir(parents=True, exist_ok=True)
    OUT_GT.mkdir(parents=True, exist_ok=True)
    for n, spec in enumerate(build_specs()):
        pdf = render_text_pdf(spec)
        if spec.render_mode != "text":
            pdf = rasterize(pdf, low_quality=spec.render_mode == "low_quality_scan", seed=n)
        (OUT_PDF / f"{spec.doc_id}.pdf").write_bytes(pdf)
        gt = ground_truth(spec).model_dump(mode="json")
        (OUT_GT / f"{spec.doc_id}.json").write_text(json.dumps(gt, indent=2) + "\n")
        print(f"wrote {spec.doc_id} ({spec.render_mode})")


if __name__ == "__main__":
    main()
