# Cursor / Claude Build Prompts — Project 2

## Phase 0 — plan

Read PROJECT_BRIEF.md and ARCHITECTURE.md. Inspect the workspace and propose milestones.
Do not write code yet. Keep the first version local and free. Identify OS-specific requirements
for PDF extraction and optional OCR. Do not connect AWS or paid model APIs.

## Phase 1 — scaffold

Create a Next.js/TypeScript frontend and FastAPI/Pydantic backend.
Add health check, upload endpoint skeleton, environment example, gitignore, and README.
Do not add cloud dependencies.

## Phase 2 — synthetic invoice dataset

Generate at least 12 fictional invoice PDFs and corresponding ground-truth JSON.
Make examples varied as described in PROJECT_BRIEF.md.
Clearly mark them synthetic. Add a script to regenerate the dataset.
Do not use real people's or companies' financial information.

## Phase 3 — safe upload and extraction

Implement file validation, size limits, safe filenames, local storage, PDF text extraction,
page-aware extraction metadata, and error handling.
Add tests for invalid types, oversized files, empty PDFs, and malformed PDFs.

## Phase 4 — normalization and validation

Implement typed Pydantic schemas and deterministic invoice validation.
Preserve evidence/source page references for extracted fields.
Do not silently fill missing values. Add tests against ground truth.

## Phase 5 — UI and review

Build upload, document list, extraction detail, validation warnings, evidence display,
manual correction, and reviewed status. Include loading, empty, and error states.
No payment actions or external side effects.

## Phase 6 — agent explanation

Add a mock agent/explainer that summarizes deterministic validation results.
It must not invent extracted values or label a possible duplicate as fraud.
Add optional model integration only after explaining API costs and credentials.

## Phase 7 — optional AWS adapters

Propose a separate plan for S3, Textract, Bedrock, Step Functions, IAM, and CloudWatch.
Do not provision resources or incur costs without explicit approval.
Keep local adapters working when AWS is not configured.

## Phase 8 — finish

Run tests and static checks. Compare extraction results to ground-truth JSON.
Document limitations, OCR setup, local run steps, and optional AWS cost considerations.
Report only checks actually run.
