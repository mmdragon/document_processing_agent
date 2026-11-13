# Document Processing Agent

A local-first web app for reviewing **synthetic** PDF invoices. You upload an invoice, and the app:
- extracts the structured fields, keeping the page and line each value came from
- runs deterministic checks on the arithmetic, required fields and dates
- flags possible duplicates
- explains the results in plain language
- lets a person correct values and mark the document reviewed

**Safety:** the app can't approve payments, send money, contact vendors or change source files, and it never overwrites extracted values. Use synthetic documents only, and never commit real financial documents.

All eight build phases are complete (see [docs/BUILD_PROMPTS.md](docs/BUILD_PROMPTS.md)). The optional AWS adapters are planned but not built: [docs/AWS_PLAN.md](docs/AWS_PLAN.md).

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router) + TypeScript + Tailwind |
| Backend | FastAPI + Pydantic, Python 3.12 managed by [uv](https://docs.astral.sh/uv/) |
| PDF text | PyMuPDF (rows and columns rebuilt from word positions) |
| OCR (optional) | Tesseract, used through PyMuPDF |
| Storage | Local files under `backend/data/uploads/`, records in SQLite (standard-library `sqlite3`) |
| Validation | Plain Python rules (deterministic) |
| Explainer | Template-based mock with output guardrails; no model, no API cost |

## Quick start (macOS)

Prerequisites:
- [uv](https://docs.astral.sh/uv/getting-started/installation/). It installs Python 3.12 for you, so the system Python isn't used.
- Node.js 20 or newer, and npm.

Backend on http://localhost:8000 (interactive API docs at `/docs`):

```bash
cd backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

Frontend on http://localhost:3000:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000 and drop in a PDF from `backend/sample_data/invoices/`. It's uploaded and processed straight away. Click **Open review** to see:

- **Extracted fields:** each value with its confidence and source line. Uncertain fields are highlighted. **Correct** or **Add** a value: dates as `YYYY-MM-DD`, amounts as plain numbers like `1234.50`, currency as a 3-letter code. The extracted value stays visible, crossed out, next to your correction, and every change goes into the correction history.
- **Summary:** a plain-language explanation that labels facts, interpretations and questions, with suggested next steps and a **Download review report (.md)** button.
- **Validation:** issues (errors, warnings, notes) and every check with its result. It re-runs after each correction.
- **Source:** the original file shown inline, plus the extracted text for each page.
- **Review:** **Mark as reviewed** (with an optional note) locks the document, and **Reopen for edits** unlocks it. Marking a document reviewed records that a person checked it. It does not approve payment.

## OCR setup (optional)

Without OCR, image-only pages (scans, PNG or JPEG) get the status `needs_ocr`. You can still type the key fields in by hand on the review page, and they'll be checked.

To read scans automatically:

```bash
brew install tesseract
```
```bash
tesseract --version
```

Then restart the backend and click **Re-run extraction** on the scanned document. The backend uses OCR only when `OCR_ENABLED=true` (the default) **and** the `tesseract` program is on `PATH`. If PyMuPDF can't find Tesseract's language data, set `TESSDATA_PREFIX` to the folder that contains `eng.traineddata`, for example `$(brew --prefix)/share/tessdata`.

If `brew install` fails because `/opt/homebrew` isn't writable, Homebrew belongs to another macOS user account. Install from that account, or change ownership only if no one else uses that Homebrew.

OCR'd values always get lower confidence and are flagged for review. Expect errors on `inv11_low_quality_scan`.

## Sample data and evaluation

`backend/sample_data/` holds 14 fictional invoices (12 with a text layer and 2 image-only scans), each with a ground-truth JSON file. Every file is marked synthetic. [backend/sample_data/README.md](backend/sample_data/README.md) lists the scenarios.

Regenerate the dataset (running it again gives byte-identical output):

```bash
cd backend && uv run python scripts/generate_invoices.py
```

Score the pipeline against the ground truth. This runs the same code as the API, with no server or database:

```bash
cd backend && uv run python scripts/evaluate.py
```

Add `--json results.json` to save the details, or `--ocr` to use Tesseract if it's installed. The script exits with code 1 if any text-layer invoice has a wrong field, a missed issue or a false alarm.

Latest result (without OCR):

| Scope | Documents | Fields correct | Line-item tables exact | Issues missed | False alarms |
|---|---:|---:|---:|---:|---:|
| Text-layer PDFs | 12 | 156/156 (100%) | 12/12 | 0 | 0 |
| All samples | 14 | 163/182 (90%) | 12/14 | 1 | 0 |

Without OCR, neither scan has any fields read (both are correctly flagged `ocr_required`). The one missed issue is `low_quality_scan` on `inv11`, because detecting it needs OCR confidence, which isn't implemented. These numbers come from a ruleset tuned on this synthetic layout, so they say nothing about real-world invoices.

## Checks

```bash
cd backend && uv run ruff check . && uv run ruff format --check . && uv run pytest
```
```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run build
```

Last run, 2026-11-12:
- **ruff:** clean.
- **pytest:** 198 passed, 1 skipped (the real-Tesseract test, since Tesseract isn't installed).
- **Frontend:** type check, lint and production build all clean.
- **Evaluation:** exit code 0.
- **Dataset:** regenerating it gives byte-identical files.

Don't run `npm run build` while `npm run dev` is running. Both write to `frontend/.next`, so the build breaks the dev server. If that happens, delete `frontend/.next` and restart the dev server.

## Configuration

Copy `.env.example`: the backend values go in `backend/.env` and `NEXT_PUBLIC_API_BASE_URL` goes in `frontend/.env.local`. The defaults work without any changes.

| Variable | Default | Purpose |
|---|---|---|
| `UPLOAD_DIR` | `backend/data/uploads` | Where originals are stored (outside the frontend) |
| `DATABASE_PATH` | `backend/data/documents.sqlite3` | SQLite file |
| `MAX_UPLOAD_BYTES` | `10485760` | Upload size limit |
| `MAX_PAGES` | `50` | Page limit |
| `MIN_TEXT_CHARS_PER_PAGE` | `20` | Below this, a page counts as having no text layer |
| `OCR_ENABLED` / `OCR_LANGUAGE` | `true` / `eng` | Tesseract OCR, if installed |
| `EXPLAINER_MODE` | `mock` | The only mode implemented |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | Allowed browser origins |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Backend URL for the frontend |

## How it works

```
upload ─► checks (type, signature, size, structure) ─► store as <uuid>.<ext>
process ─► page text (PyMuPDF; Tesseract for pages with no text) ─► rows and cells
        ─► fields with evidence ─► latest corrections applied ─► deterministic checks + duplicate lookup
        ─► status: processed | needs_review | needs_ocr | failed
review  ─► corrections (logged, re-validated) ─► summary + report ─► mark reviewed
```

### Fields

Each field records its `value`, the exact `raw` text, a `status` (`found`, `missing`, `ambiguous` or `unparseable`), a `confidence`, and `evidence` (page number and source line). Nothing is guessed:
- Missing fields stay `null`.
- `04/05/2026` stays ambiguous, with both possible readings given.
- Two-digit years are left unread.
- A due date is never calculated from payment terms.
- Values read by layout position or OCR get lower confidence, and anything under 0.8 is flagged.

### Validation (`backend/app/validation/invoice.py`)

| Check | Issue code | Severity |
|---|---|---|
| Vendor, invoice number, invoice date and total are present | `missing_*` | error |
| Due date and currency are present | `missing_due_date`, `missing_currency` | warning |
| Each line amount = qty × unit price (rounded half up) | `line_item_amount_mismatch` | error |
| Subtotal = sum of line amounts | `subtotal_mismatch` | error |
| Total = subtotal − discount + tax + shipping (components that aren't printed count as 0, and the check says which) | `total_mismatch` | error |
| Dates are unambiguous, and the due date isn't before the invoice date | `ambiguous_date`, `unparseable_date`, `due_before_invoice_date` | warning |
| Same normalized vendor + invoice number as an earlier document, or an identical file | `possible_duplicate` | warning |

Money comparisons allow a difference of up to 0.01. Every check records whether it passed, failed or was skipped, with the numbers it used.

### Explainer and guardrails (`backend/app/agents/`)

The explainer only describes what the pipeline already found: the extracted fields with their sources, the check results, possible duplicates, questions about anything ambiguous, and next review steps. It has no tools and causes no side effects.

Every output is checked. The guardrails reject:
- any money amount or ISO date that doesn't already appear in the document's data
- any use of "fraud" that isn't explicitly negated
- wording that approves, authorizes or sends payment
- describing a duplicate as certain

If a future model-based explainer fails these checks or crashes, the template explainer is used instead and the reason is recorded.

**Hosted model (not enabled).** A model-backed explainer would need credentials kept only in `backend/.env`. It would also cost money per token: a summary here is roughly 2–4K tokens in and a few hundred out, which is a fraction of a cent to a few cents per document, so results should be cached per document version. And it would send document data to the provider, so use synthetic data only. [docs/AWS_PLAN.md](docs/AWS_PLAN.md) has current Bedrock and Textract figures.

## API

| Method | Path | Notes |
|---|---|---|
| GET | `/api/health` | `{"status": "ok"}` |
| POST | `/api/documents` | Upload (multipart `file`). Returns the summary with status `uploaded`. |
| GET | `/api/documents` | Lists documents, newest first |
| GET | `/api/documents/{id}` | Summary, page text, `fields` (as extracted), `corrections`, `validation` (run on the corrected values) |
| POST | `/api/documents/{id}/process` | Extract, read fields, validate. Returns 409 if the document is `reviewed` or already `processing`. |
| POST | `/api/documents/{id}/corrections` | `{"corrections": [{"field", "value", "note"}]}`. Values are checked strictly (422 names the `field`), then validation re-runs. Returns 409 if the document is reviewed or unprocessed. |
| POST | `/api/documents/{id}/review` | `{"reviewed": true, "note"}` marks it reviewed and locks it. `{"reviewed": false}` reopens it. |
| GET | `/api/documents/{id}/explanation` | Summary with `fact` / `interpretation` / `question` items, next steps, the explainer's name, whether a model wrote it, and the guardrail result |
| GET | `/api/documents/{id}/report?format=json\|markdown` | Review report: field values after corrections, each with its source and evidence, plus issues, checks, corrections and the summary. Returns 409 until processed. |
| GET | `/api/documents/{id}/file` | The original upload, shown inline (`nosniff`, `no-store`) |

App errors come back as `{"detail": {"code", "message"}}` (or `{"detail": "..."}` for 404 and 409). Malformed request bodies get FastAPI's standard 422 list.

## Security notes

- Uploads must be PDF, PNG or JPEG, and the extension **and** the file's signature bytes must match. The stored content type comes from the signature.
- Oversized (413), empty (400), malformed, password-protected and over-long (422) files are rejected before they're stored. Partial files are always deleted.
- Files are stored only under server-generated UUID names, outside the frontend. Client file names are kept only for display, with any folder path and control characters removed.
- Uploaded files are opened read-only and never executed. Originals are never modified or deleted by the app.
- Logs contain document IDs, statuses and issue codes only, never document text or field values.
- `.env`, uploads and the database are gitignored. No credentials are needed or stored.

## Limitations

- **Layout-specific field reading.** The rules look for common labels, a Description/Amount table, and a vendor block at the top left. Real invoices with other layouts will often come out as `needs_review` with missing fields.
- **OCR is optional and unmeasured here.** The real-Tesseract test is skipped because Tesseract isn't installed, `low_quality_scan` isn't detected, and line items can't be corrected.
- **Duplicate detection depends on order.** A document is only compared with documents processed before it.
- **Tax rates aren't checked** against the printed percentage.
- **Processing runs inside the request.** If the server crashes mid-process, the document can be left in `processing`.
- **No user accounts.** Anyone who can reach the app can review, and corrections aren't tied to a named person.
- **The guardrails match patterns.** They catch invented amounts and dates and specific forbidden wording, but they can't judge whether a sentence is reasonable.
- **Known dependency advisories.** `npm audit --omit=dev` reports none. The full `npm audit` still lists a moderate `minimatch` advisory in the ESLint tooling (dev-only, never shipped to the browser or server).
- **No AWS.** [docs/AWS_PLAN.md](docs/AWS_PLAN.md) proposes optional S3, Textract, Bedrock, Step Functions, IAM and CloudWatch adapters, with costs, least-privilege IAM, an approval step for each stage, and teardown. Nothing has been provisioned.

## Layout

```
backend/
  app/            main.py, config.py, uploads.py, processing.py, review.py, reporting.py,
                  api/, extraction/, normalization/, validation/, agents/,
                  repositories/, schemas/
  scripts/        generate_invoices.py, evaluate.py
  sample_data/    invoices/ + ground_truth/ (synthetic)
  tests/
  data/           runtime uploads and DB (gitignored)
frontend/
  app/            home (upload + list), documents/[id] (review)
  components/     UploadPanel, DocumentList, FieldsTable, ExplanationPanel, ValidationPanel, ...
  lib/            api.ts (typed client), format.ts
docs/             project brief, architecture, build prompts, AWS plan
```
