# Document Processing Agent

A local-first web app for processing **synthetic** PDF invoices. You upload an invoice, and the app extracts structured fields, checks the arithmetic and required fields, flags possible duplicates, and shows a review screen.

> **Status: Phase 3 (safe upload and extraction).** Uploads are checked and stored, documents are recorded in SQLite, and text is extracted page by page with PyMuPDF. Optional OCR runs when Tesseract is installed. There are 14 synthetic invoices with ground truth. Field extraction, validation, the review UI and the agent explainer come in later phases (see [docs/BUILD_PROMPTS.md](docs/BUILD_PROMPTS.md)).

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
| GET | `/api/documents/{id}` | Summary plus the extraction result (text for each page, method, warnings) |
| POST | `/api/documents/{id}/process` | Runs text extraction. The status becomes `extracted`, `needs_ocr` or `failed`. Returns 409 if the document is `reviewed` or already `processing`. |

Upload rules:
- Only PDF, PNG and JPEG are accepted. The extension **and** the file's signature bytes must match, and the stored content type comes from the signature, not from the client.
- Files over 10 MB get 413, and empty files get 400.
- Malformed or password-protected PDFs, and documents over 50 pages, get 422.
- Files are stored as `backend/data/uploads/<uuid>.<ext>`. The client's file name is kept only for display, with any folder path and control characters removed.
- Errors come back as `{"detail": {"code", "message"}}`.
- Logs contain document IDs and statuses only, never document text.

Processing statuses: `uploaded`, then `processing`, then one of `extracted`, `needs_ocr` or `failed`. (`reviewed` arrives in Phase 5.)

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

- Extraction produces raw text for each page only. Structured fields (vendor, totals and so on) come in Phase 4.
- The real OCR path has a test, but it's skipped unless `tesseract` is installed. Expect OCR errors on `inv11_low_quality_scan`.
- Processing runs synchronously inside the request. If the server crashes mid-process, the document can be left in `processing` status.
- There's no UI for uploads yet (Phase 5). Use the API docs at `/docs`.
- No AWS integration. The optional Phase 7 adapters will be planned separately, with cost notes, before anything is provisioned.
