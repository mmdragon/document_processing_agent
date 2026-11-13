"""Rule-based FieldExtractor: page lines -> typed invoice fields with evidence.

Deterministic and label-driven. When a label or value is not found the field stays
``missing``; ambiguous values keep their raw text and get no value.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal

from app.extraction.models import ExtractionResult, TextLine
from app.normalization.parsers import (
    detect_currency,
    has_explicit_currency_code,
    parse_date,
    parse_number,
)
from app.schemas.invoice import Evidence, ExtractedField, InvoiceFields, LineItem

OCR_CONFIDENCE_FACTOR = 0.7  # OCR'd values always fall below the review threshold
LABELED = 0.95
LAYOUT = 0.85  # values found by position rather than by a label


@dataclass
class _Line:
    page: int
    method: str  # "text" | "ocr"
    line: TextLine

    @property
    def cells(self) -> list[str]:
        return [c.text.strip() for c in self.line.cells]

    @property
    def text(self) -> str:
        return self.line.text


def _rx(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


# Label patterns for "Label: value" cells. The value may also be in the next cell.
_LABELS: dict[str, re.Pattern[str]] = {
    "invoice_number": _rx(
        r"^(?:invoice\s*(?:no\.?|number|num\.?|#)|inv\.?\s*(?:no\.?|#))\s*[:#]?\s*(?P<v>.*)$"
    ),
    "invoice_date": _rx(
        r"^(?:invoice\s+date|date\s+of\s+issue|issue\s+date|date)\s*:\s*(?P<v>.*)$"
    ),
    "due_date": _rx(r"^(?:due\s+date|payment\s+due|date\s+due)\s*:?\s*(?P<v>.*)$"),
    "purchase_order_number": _rx(
        r"^(?:p\.?\s?o\.?(?:\s*(?:number|no\.?|#))?|purchase\s+order(?:\s+(?:number|no\.?))?)"
        r"\s*:\s*(?P<v>.*)$"
    ),
    "payment_terms": _rx(r"^(?:payment\s+)?terms\s*:\s*(?P<v>.*)$"),
}

_TOTALS: dict[str, re.Pattern[str]] = {
    "subtotal": _rx(r"^sub\s*-?\s*total\b"),
    "discount": _rx(r"^(?:less\s+)?discount\b"),
    "tax": _rx(r"^(?:sales\s+)?tax\b|^vat\b|^gst\b|^hst\b"),
    "shipping": _rx(r"^(?:shipping|freight|delivery|postage)\b"),
    "total": _rx(r"^(?:total|invoice\s+total|amount\s+due|balance\s+due|total\s+due)\b"),
}

_BLOCK_STOP = _rx(r"^(?:bill|ship|sold)\s+to\b")
_TITLE = _rx(r"^(?:tax\s+)?invoice$")
_BANNER = _rx(r"synthetic\s+sample")


class RuleBasedFieldExtractor:
    """FieldExtractor: extract_fields(extraction) -> InvoiceFields."""

    def extract_fields(self, extraction: ExtractionResult) -> InvoiceFields:
        lines = [
            _Line(page.page_number, page.method, line)
            for page in extraction.pages
            if page.method in ("text", "ocr")
            for line in page.lines
        ]
        fields = InvoiceFields()
        if not lines:
            fields.extraction_notes.append("No text available to extract fields from.")
            return fields

        self._vendor(lines, fields)
        self._labeled(lines, fields)
        table_end = self._line_items(lines, fields)
        self._totals(lines[table_end:], fields)
        self._currency(lines, fields)
        return fields

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _found(value, raw: str, src: _Line, confidence: float, note: str | None = None):
        if src.method == "ocr":
            confidence *= OCR_CONFIDENCE_FACTOR
        return ExtractedField(
            value=value,
            raw=raw,
            status="found",
            confidence=round(confidence, 2),
            evidence=Evidence(page_number=src.page, line=src.text, method=src.method),
            note=note,
        )

    @staticmethod
    def _unresolved(status: str, raw: str, src: _Line, note: str) -> ExtractedField:
        return ExtractedField(
            value=None,
            raw=raw,
            status=status,
            confidence=0.0,
            evidence=Evidence(page_number=src.page, line=src.text, method=src.method),
            note=note,
        )

    # ------------------------------------------------------------------ vendor

    def _vendor(self, lines: list[_Line], fields: InvoiceFields) -> None:
        first_page = [ln for ln in lines if ln.page == lines[0].page]
        for idx, ln in enumerate(first_page):
            head = ln.cells[0] if ln.cells else ""
            if not head or _BANNER.search(ln.text) or _TITLE.match(head) or self._is_label(head):
                continue
            fields.vendor_name = self._found(
                head, head, ln, LAYOUT, "Taken from the top-left of the first page."
            )
            x0 = ln.line.cells[0].x0
            address: list[str] = []
            first_address_line: _Line | None = None
            last_y = ln.line.y
            for nxt in first_page[idx + 1 :]:
                if nxt.line.y - last_y > 30 or len(address) >= 4:
                    break
                cell = next((c for c in nxt.line.cells if abs(c.x0 - x0) < 6), None)
                if cell is None:
                    continue  # a row that belongs to another column (e.g. invoice meta)
                if _BLOCK_STOP.match(cell.text) or self._is_label(cell.text):
                    break
                address.append(cell.text.strip())
                first_address_line = first_address_line or nxt
                last_y = nxt.line.y
            if address:
                joined = ", ".join(address)
                fields.vendor_address = self._found(
                    joined,
                    "\n".join(address),
                    first_address_line or ln,
                    0.8,
                    "Lines printed under the vendor name.",
                )
            return

    @staticmethod
    def _is_label(text: str) -> bool:
        return any(p.match(text) for p in _LABELS.values())

    # ------------------------------------------------------------------ labeled fields

    def _labeled(self, lines: list[_Line], fields: InvoiceFields) -> None:
        for name, pattern in _LABELS.items():
            hit = self._find_label(lines, pattern)
            if hit is None:
                continue
            raw, src = hit
            if not raw:
                setattr(
                    fields,
                    name,
                    self._unresolved("missing", "", src, "Label is printed but has no value."),
                )
                continue
            if name in ("invoice_date", "due_date"):
                parsed = parse_date(raw)
                if parsed.status == "found":
                    setattr(fields, name, self._found(parsed.value, raw, src, LABELED))
                elif parsed.status == "ambiguous":
                    options = " or ".join(d.isoformat() for d in parsed.candidates)
                    setattr(
                        fields,
                        name,
                        self._unresolved(
                            "ambiguous", raw, src, f"'{raw}' could be {options}; not guessed."
                        ),
                    )
                else:
                    setattr(
                        fields,
                        name,
                        self._unresolved(
                            "unparseable", raw, src, f"'{raw}' is not a recognised date."
                        ),
                    )
            else:
                setattr(fields, name, self._found(raw, raw, src, LABELED))

    @staticmethod
    def _find_label(lines: list[_Line], pattern: re.Pattern[str]) -> tuple[str, _Line] | None:
        for ln in lines:
            cells = ln.cells
            for i, cell in enumerate(cells):
                m = pattern.match(cell)
                if not m:
                    continue
                value = m.group("v").strip()
                if not value and i + 1 < len(cells):
                    value = cells[i + 1]
                return value, ln
        return None

    # ------------------------------------------------------------------ line items

    def _line_items(self, lines: list[_Line], fields: InvoiceFields) -> int:
        """Parse the item table; return the index of the first line after it."""
        header = next(
            (
                i
                for i, ln in enumerate(lines)
                if any(c.lower().startswith("description") for c in ln.cells)
                and any(c.lower() in ("amount", "total", "line total") for c in ln.cells)
            ),
            None,
        )
        if header is None:
            fields.extraction_notes.append("No line-item table header was found.")
            return 0

        idx = header + 1
        for idx, ln in enumerate(lines[header + 1 :], start=header + 1):
            cells = ln.cells
            if cells and any(p.match(cells[0]) for p in _TOTALS.values()):
                return idx
            item = self._parse_item(ln)
            if item is not None:
                fields.line_items.append(item)
            elif len(cells) == 1 and fields.line_items:
                # A wrapped description line.
                prev = fields.line_items[-1]
                prev.description = f"{prev.description} {cells[0]}"
            else:
                fields.extraction_notes.append(
                    f"Page {ln.page}: could not read table row '{ln.text}'."
                )
        return idx + 1

    @staticmethod
    def _parse_item(ln: _Line) -> LineItem | None:
        cells = ln.cells
        if len(cells) < 4:
            return None
        qty, unit, amount = (parse_number(c) for c in cells[-3:])
        if qty is None or unit is None or amount is None:
            return None
        return LineItem(
            description=" ".join(cells[:-3]),
            quantity=qty,
            unit_price=unit,
            amount=amount,
            evidence=Evidence(page_number=ln.page, line=ln.text, method=ln.method),
        )

    # ------------------------------------------------------------------ totals

    def _totals(self, lines: list[_Line], fields: InvoiceFields) -> None:
        for name, pattern in _TOTALS.items():
            match: tuple[Decimal, str, _Line] | None = None
            for ln in self._two_column_rows(lines):
                label, raw = ln.cells[0], ln.cells[-1]
                if name != "subtotal" and _TOTALS["subtotal"].match(label):
                    continue
                if pattern.match(label):
                    value = parse_number(raw)
                    if value is not None:
                        match = (value, raw, ln)  # keep the last one (e.g. final total)
            if match is None:
                continue
            value, raw, ln = match
            note = None
            if name == "discount" and value < 0:
                value, note = -value, "Printed as a negative amount; stored as positive."
            setattr(fields, name, self._found(value, raw, ln, LABELED, note))

    @staticmethod
    def _two_column_rows(lines: list[_Line]) -> Iterator[_Line]:
        for ln in lines:
            if 2 <= len(ln.cells) <= 3:
                yield ln

    # ------------------------------------------------------------------ currency

    def _currency(self, lines: list[_Line], fields: InvoiceFields) -> None:
        sources = [f.evidence for f in (fields.total, fields.subtotal) if f.evidence]
        sources += [i.evidence for i in fields.line_items]
        for ev in sources:
            if has_explicit_currency_code(ev.line):
                src = next(ln for ln in lines if ln.text == ev.line and ln.page == ev.page_number)
                code = detect_currency(ev.line)
                fields.currency = self._found(code, code, src, LABELED)
                return
        for ev in sources:
            code = detect_currency(ev.line)
            if code:
                src = next(ln for ln in lines if ln.text == ev.line and ln.page == ev.page_number)
                note = "Inferred from a currency symbol; no currency code is printed."
                confidence = 0.6 if code == "USD" else LAYOUT
                if code == "USD":
                    note += " '$' is used by several currencies."
                fields.currency = self._found(code, code, src, confidence, note)
                return
