# Synthetic invoice dataset

**Every file here is synthetic.** All vendors, customers, addresses and numbers are made up. Each PDF has a "SYNTHETIC SAMPLE" banner and footer, and its PDF title metadata says so too. Never put real invoices in this folder.

Regenerate the dataset (from `backend/`):

```bash
uv run python scripts/generate_invoices.py
```

Running it again produces byte-identical files. The scanned samples use seeded noise.

## What the ground truth means

`ground_truth/<id>.json` records **what is printed on the document**, not what "should" be correct. For example, `inv04` stores the wrong printed total, and `total_mismatch` appears in `expected_issues`.

- If a field isn't on the document, it's `null` (it is never inferred).
- Each date has a `*_raw` field with the exact printed text, plus a parsed ISO `date`. The parsed date is `null` when the printed date is ambiguous.
- Money and quantities are stored as decimal strings.
- `expected_extraction_method` is `text` for PDFs with a text layer and `ocr` for image-only scans.

Schema: [`app/schemas/ground_truth.py`](../app/schemas/ground_truth.py). The dataset's internal consistency is checked by [`tests/test_sample_data.py`](../tests/test_sample_data.py).

## Samples

| ID | Scenario | What it tests | Expected issues |
|---|---|---|---|
| inv01_normal | normal | Correct items, 8.25% tax, PO number | none |
| inv02_missing_invoice_number | missing_invoice_number | No invoice number printed | missing_invoice_number |
| inv03_missing_due_date | missing_due_date | Terms say "Net 30" but no due date is printed. The app must not compute one silently. | missing_due_date |
| inv04_arithmetic_mismatch | arithmetic_mismatch | Printed total 763.70, but the subtotal is 736.70 | total_mismatch |
| inv05_duplicate | duplicate | Same vendor and invoice number as inv01, re-sent later | possible_duplicate |
| inv06_multiple_line_items | multiple_line_items | 9 items, including a fractional quantity (6.5 hours) | none |
| inv07_discount | discount | 10% discount before the total | none |
| inv08_tax_and_shipping | tax_and_shipping | Sales tax plus untaxed shipping | none |
| inv09_scanned | scanned_image | Clean image-only PDF with no text layer | ocr_required |
| inv10_unusual_date_format | unusual_date_format | "Tuesday, 3rd February 2026" and "2026/03/05" | none |
| inv11_low_quality_scan | low_quality_ocr | 100 dpi, blurred, rotated 1.4°, noisy, heavy JPEG compression | ocr_required, low_quality_scan |
| inv12_non_usd_currency | non_usd_currency | EUR with European number format (1.825,00 €), 20% VAT, DD.MM.YYYY dates | none |
| inv13_ambiguous_date | ambiguous_date | "04/05/2026" could be April 5 or May 4 | ambiguous_date |
| inv14_line_item_mismatch | line_item_mismatch | Line prints 351.00, but 14 × 22.50 = 315.00 | line_item_amount_mismatch |

Note: inv01 and inv05 match each other on vendor + invoice number. Whichever one is processed second should be flagged as a **possible** duplicate. That flag is never a fraud finding.
