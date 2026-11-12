# Architecture — Document Processing Agent

## Flow

Next.js upload UI → FastAPI → file validation/storage → extraction adapter → normalization →
deterministic validation → optional agent explanation → review UI.

## Suggested structure

document-processing-agent/
  frontend/
    app/
    components/
    lib/
  backend/
    app/
      main.py
      api/
      extraction/
      normalization/
      validation/
      agents/
      repositories/
      schemas/
    tests/
    sample_data/
      invoices/
      ground_truth/
  docs/
  .env.example
  .gitignore
  README.md

## Security requirements

- Allow only expected PDF/image types; verify file signatures where practical.
- Enforce file-size limits.
- Generate server-side file names; never trust uploaded paths.
- Store uploads outside publicly served frontend assets.
- Do not execute uploaded content.
- Avoid logging full document contents or sensitive extracted data.
- Delete temporary files when processing finishes or fails.
- Keep API credentials server-side.
- Clearly distinguish extracted facts from model-generated interpretation.

## API outline

GET /api/health
POST /api/documents
GET /api/documents
GET /api/documents/{document_id}
POST /api/documents/{document_id}/process
POST /api/documents/{document_id}/review
GET /api/documents/{document_id}/report

## Processing interfaces

DocumentExtractor:
- extract_text(file_path) -> extracted text + page references + extraction metadata.

FieldExtractor:
- extract_fields(text) -> normalized fields + evidence + unknowns.

InvoiceValidator:
- validate(fields) -> deterministic issues and checks.

AgentExplainer:
- explain(validation_result) -> human-readable explanation.
Use a mock explainer first; optional hosted model later.

## Validation examples

- subtotal equals sum of line item amounts (within defined rounding tolerance).
- total equals subtotal + tax + shipping - discount (according to available fields).
- required vendor and invoice fields exist.
- invoice date is parseable.
- possible duplicate key: normalized vendor + invoice number.
- missing or ambiguous values are "needs review", not guessed.
