# Document Processing Agent

A local-first web app for processing **synthetic** PDF invoices. You upload an invoice, and the app extracts structured fields, checks the arithmetic and required fields, flags possible duplicates, and shows a review screen.

> **Status: Phase 4 (fields and validation).** Uploads are checked and stored in SQLite. Text is extracted page by page (with optional OCR), invoice fields are read with the page and line they came from, and deterministic checks run on the math, required fields, dates and possible duplicates. All 14 synthetic invoices match their ground truth. The review UI and the agent explainer come in later phases (see [docs/BUILD_PROMPTS.md](docs/BUILD_PROMPTS.md)).

**Safety:** this tool never approves payments, sends money, contacts vendors or changes source files. Use synthetic documents only, and never commit real financial documents.

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 15 (App Router) + TypeScript + Tailwind |
| Backend | FastAPI + Pydantic, Python 3.12 managed by [uv](https://docs.astral.sh/uv/) |
| PDF extraction | PyMuPDF |
| Optional OCR | Tesseract, used through PyMuPDF |
| Persistence | SQLite (Python standard library `sqlite3`) |
| Agent | Mock explainer first; a hosted model only after cost review |

## Prerequisites (macOS)

- [uv](https://docs.astral.sh/uv/getting-started/installation/). It installs Python 3.12 for you, so the system Python 3.9 isn't used.
- Node.js 20 or newer and npm
- Optional, only for scanned or image invoices: `brew install tesseract`. Restart the backend after installing. Without Tesseract, image-only pages get the status `needs_ocr` instead of failing.

## Run locally

Backend (http://localhost:8000; API docs at `/docs`):

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Frontend (http://localhost:3000):

```bash
cd frontend
npm install
npm run dev
```

The home page shows a badge saying whether the frontend can reach the backend.

## Configuration

Copy `.env.example`: the backend values go in `backend/.env` and `NEXT_PUBLIC_API_BASE_URL` goes in `frontend/.env.local`. The defaults work without any changes.

## Checks

```bash
cd backend && uv run pytest && uv run ruff check . && uv run ruff format --check .
cd frontend && npm run lint && npx tsc --noEmit && npm run build
```

## API (current)

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | Returns `{"status": "ok"}` |
| POST | `/api/documents` | Upload (multipart `file`). See the upload rules below. Returns the document summary with status `uploaded`. |
| GET | `/api/documents` | Lists documents, newest first |
| GET | `/api/documents/{id}` | Summary, extracted page text, invoice `fields` (each with value, raw text, status, confidence and evidence) and `validation` (issues and checks) |
| POST | `/api/documents/{id}/process` | Runs extraction, field reading and validation. The status becomes `processed`, `needs_review`, `needs_ocr` or `failed`. Returns 409 if the document is `reviewed` or already `processing`. |

Upload rules:
- Only PDF, PNG and JPEG are accepted. The extension **and** the file's signature bytes must match, and the stored content type comes from the signature, not from the client.
- Files over 10 MB get 413, and empty files get 400.
- Malformed or password-protected PDFs, and documents over 50 pages, get 422.
- Files are stored as `backend/data/uploads/<uuid>.<ext>`. The client's file name is kept only for display, with any folder path and control characters removed.
- Errors come back as `{"detail": {"code", "message"}}`.
- Logs contain document IDs and statuses only, never document text.

Processing statuses: `uploaded`, then `processing`, then one of:
- `processed`: every check passed and no field needs review.
- `needs_review`: at least one issue, or an ambiguous or low-confidence field.
- `needs_ocr`: no text layer, and OCR isn't available.
- `failed`: see `error`.

(`reviewed` arrives in Phase 5.)

## Fields and validation

Each field records its `value`, the exact `raw` text, a `status` (`found`, `missing`, `ambiguous` or `unparseable`), a `confidence`, and `evidence` (the page number and source line). Values are never guessed:
- Missing fields stay `null`.
- An ambiguous date like `04/05/2026` keeps its raw text with no value, and a note gives both possible readings.
- A due date is never calculated from payment terms.
- Fields read by OCR or by layout position get lower confidence. Anything under 0.8 is flagged for review.

The checks are all plain Python rules (no model is involved), in `backend/app/validation/invoice.py`:

| Check | Issue code | Severity |
|---|---|---|
| Vendor, invoice number, invoice date and total are present | `missing_*` | error |
| Due date and currency are present | `missing_due_date`, `missing_currency` | warning |
| Each line amount = qty × unit price (rounded half up) | `line_item_amount_mismatch` | error |
| Subtotal = sum of line amounts | `subtotal_mismatch` | error |
| Total = subtotal − discount + tax + shipping (components that aren't printed count as 0, and the check says which) | `total_mismatch` | error |
| Dates can be read unambiguously, and the due date isn't before the invoice date | `ambiguous_date`, `unparseable_date`, `due_before_invoice_date` | warning |
| Same normalized vendor + invoice number as an earlier document, or an identical file | `possible_duplicate` | warning |

Money comparisons allow a difference of up to 0.01. A possible duplicate is only a flag for a person to check. It is never treated as a fraud finding.

The planned endpoints (list, detail, process, review, report) are listed in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Sample data

`backend/sample_data/` holds 14 synthetic invoice PDFs with a matching ground-truth JSON for each. Regenerate them with `cd backend && uv run python scripts/generate_invoices.py`. See [backend/sample_data/README.md](backend/sample_data/README.md) for the scenarios.

## Layout

```
backend/
  app/            main.py, config.py, api/, extraction/, normalization/,
                  validation/, agents/, repositories/, schemas/
  tests/
  scripts/        generate_invoices.py (synthetic dataset)
  sample_data/    invoices/ + ground_truth/ (synthetic)
  data/           runtime uploads and DB (gitignored)
frontend/
  app/ components/ lib/
docs/             project brief, architecture, build prompts
```

## Limitations

- Field reading is rule-based. It looks for common labels ("Invoice No.", "Due Date", "Subtotal" and so on), a table with Description/Amount headers, and the vendor block at the top left. It's tuned on the synthetic layout, so other invoice layouts will often end up as `needs_review` with missing fields.
- Duplicate detection depends on order: a document is only compared with documents processed before it.
- Tax rates aren't checked against the printed percentage. The low-quality scan check (`low_quality_scan`) needs OCR confidence, which isn't implemented yet.
- The real OCR path has a test, but it's skipped unless `tesseract` is installed. Expect OCR errors on `inv11_low_quality_scan`.
- Processing runs synchronously inside the request. If the server crashes mid-process, the document can be left in `processing` status.
- There's no UI for uploads yet (Phase 5). Use the API docs at `/docs`.
- No AWS integration. The optional Phase 7 adapters will be planned separately, with cost notes, before anything is provisioned.
