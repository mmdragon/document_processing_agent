# Project 2 — AI Document Processing Agent

## 1. Product summary

Build a local-first web application where a user uploads PDF invoices and the system extracts structured
fields, validates arithmetic and required information, flags possible duplicates, and produces a review report.
The system must work with synthetic sample invoices and local processing before any AWS integration.

## 2. MVP workflow

1. User uploads a PDF invoice.
2. Backend stores it locally in a safe uploads directory.
3. Text extraction runs using PyMuPDF for text PDFs.
4. For scanned PDFs/images, optional Tesseract OCR can be used if installed.
5. Extraction layer creates normalized JSON fields.
6. Validation layer checks required fields and arithmetic.
7. Agent explains findings and may request a human review.
8. User sees extracted fields, source text/evidence, warnings, and confidence/unknown fields.
9. User can correct fields and mark the document reviewed.

## 3. Data fields

vendor_name, vendor_address, invoice_number, invoice_date, due_date, currency,
line_items[{description, quantity, unit_price, amount}], subtotal, tax, total,
purchase_order_number, payment_terms.

Store original file name, upload timestamp, processing status, extraction method, and errors.
Do not store real sensitive financial documents in a public repository.

## 4. Synthetic data

Create at least 12 synthetic invoice PDFs:
- normal invoice with correct totals;
- missing invoice number;
- missing due date;
- arithmetic mismatch;
- duplicate invoice number/vendor;
- multiple line items;
- discount;
- tax and shipping;
- scanned/image-style invoice if feasible;
- unusual date format;
- low-quality OCR sample;
- non-USD currency.

Use fictional vendor/customer names and clearly mark documents as synthetic.
Include a matching ground-truth JSON file for each invoice to support evaluation.

## 5. Agent behavior

The agent can:
- explain extracted fields;
- summarize validation issues;
- compare a document with previous local invoices for possible duplicates;
- ask for clarification when fields are ambiguous;
- generate a review summary.

The agent cannot:
- approve payment;
- send money;
- contact vendors;
- alter source PDFs;
- silently overwrite extracted values.

## 6. Local-first stack

- Frontend: Next.js + TypeScript
- Backend: FastAPI + Pydantic
- PDF extraction: PyMuPDF
- Optional OCR: Tesseract
- Local persistence: SQLite
- Deterministic validation: Python rules
- Optional LLM: provider adapter with mock mode first

## 7. Optional AWS learning phase

Only after local MVP passes tests, add optional adapters:
- S3 for object storage;
- Textract for OCR/document extraction;
- Bedrock for model inference;
- Step Functions for orchestrating a multi-step document workflow;
- IAM for least-privilege access;
- CloudWatch for logs/metrics.

Before enabling any AWS integration, explain account prerequisites, regional availability, pricing, and possible charges.
Never create cloud resources or incur costs without explicit user approval.
Do not assume Free Tier covers every service or model call.

## 8. Definition of done

- User can upload and process synthetic PDFs locally.
- Extracted fields are displayed with evidence where possible.
- Arithmetic and required-field checks are deterministic and tested.
- Duplicate detection is clearly labeled as a possible duplicate, not a definitive fraud finding.
- Unknown or low-confidence fields are marked for human review.
- Ground-truth test data exists for all sample invoices.
- No payment or external side effects are possible.
- README explains local setup, OCR requirements, sample files, limitations, and optional AWS path.
