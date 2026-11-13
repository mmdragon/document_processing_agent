# Optional AWS adapters: plan

**Status: proposal only.** No AWS account has been connected, no resources have been created, and the code makes no AWS calls. Nothing in this plan should be run until you approve each step.

The local app stays the default and keeps working without AWS. Every AWS piece is an *adapter* behind an interface that already exists or is added in step 1. Each one is turned on by an environment variable, and if it isn't configured, the local behaviour is used.

---

## 1. What AWS would add, and what it wouldn't

| Service | Role in this app | Replaces / extends | Value for this project |
|---|---|---|---|
| **S3** | Stores the uploaded originals | `backend/data/uploads/` | Low on its own. Mostly needed so Textract can read multi-page PDFs and Step Functions can pass files around |
| **Textract** | OCR for scanned and image invoices | Tesseract (not installed here) | **High.** `inv09_scanned` and `inv11_low_quality_scan` can't be processed today |
| **Bedrock** | A model-written summary | The template `MockExplainer` | Medium. Better wording, but the same guardrails apply and the mock stays as the fallback |
| **Step Functions** | Runs upload → extract → fields → validate → explain as separate steps | The in-process `process_document()` | Low for one user, and the biggest code change. Mainly a learning exercise |
| **IAM** | Least-privilege access for the app | — | Needed by everything above |
| **CloudWatch** | Logs, counters and alarms | Local uvicorn logs | Low to medium. Useful once Textract or Bedrock are costing money |

The deterministic validation, the duplicate checks, the guardrails, SQLite and the review UI **stay exactly as they are**. AWS only changes where files live, how text is read, and who writes the summary.

## 2. Before anything: account prerequisites (you do these)

1. **Account and plan.** New AWS accounts now start on a *Free plan* with $100 in credits (up to $200 with onboarding tasks). That plan lasts 6 months or until the credits run out, and the account closes at the end of it unless you upgrade to the *Paid plan*. The Free plan only covers some services. Check that Textract and Bedrock model access are allowed on your plan before relying on them. Upgrading to the Paid plan means usage beyond the credits is billed.
2. **Budget alarm first.** In AWS Budgets, create a monthly cost budget of **$5** with email alerts at 50% and 100%. That's the safety net for everything below.
3. **No root keys.** Create a user in IAM Identity Center and sign in locally with `aws sso login --profile docagent`. The app reads `AWS_PROFILE=docagent`. Don't create long-lived access keys, and never put credentials in this repo.
4. **Region.** Use **`us-east-1`** (N. Virginia) or **`us-west-2`** (Oregon). Both normally offer S3, Textract, Bedrock, Step Functions and CloudWatch, but check the region tables for Textract and for the specific Bedrock model before you start.
5. **Bedrock model access.** Anthropic models on Bedrock need a one-time access request (a use-case form) in the Bedrock console, per account and region.

## 3. Costs (checked November 2026; recheck before enabling)

Prices are per unit in US regions. Where the official page didn't show a figure, it's marked *(verify)*.

| Service | Price | Free allowance |
|---|---|---|
| Textract `DetectDocumentText` | $0.0015 / page | 1,000 pages/month for the first 3 months |
| Textract `AnalyzeExpense` | $0.01 / page | 100 pages/month for the first 3 months |
| S3 Standard | about $0.023 / GB-month storage, about $0.005 / 1,000 PUTs *(verify)*, $0.0004 / 1,000 GETs | Covered by credits |
| Step Functions (Standard) | $0.000025 / state transition | 4,000 transitions/month |
| CloudWatch Logs | about $0.50 / GB ingested *(verify)* | 5 GB/month of logs, 10 custom metrics, 10 alarms |
| Bedrock (Anthropic Haiku-class) | about $1 per 1M input tokens, $5 per 1M output tokens *(third-party figure for Haiku 4.5; verify on the Bedrock pricing page for the model you pick)* | None |

**A realistic learning run: 100 single-page synthetic invoices**

| Item | Calculation | Cost |
|---|---|---|
| Textract OCR | 100 pages × $0.0015 | $0.15 (or $0 within the free pages) |
| Textract AnalyzeExpense (optional comparison) | 100 × $0.01 | $1.00 |
| Bedrock summaries | 100 × (about 3K input + 400 output tokens) ≈ 100 × $0.005 | ≈ $0.50 |
| S3 | about 15 MB stored, a few hundred requests | < $0.01 |
| Step Functions | about 8 transitions × 100 | $0 (inside the free allowance) |
| CloudWatch | a few MB of logs | $0 (inside the free allowance) |
| **Total** | | **≈ $0.70 – $1.70** |

**What actually causes surprise bills, and how this plan avoids each:**
- **Re-running OCR or summaries on every page view.** Results are cached per document version. Textract runs only from **Re-run extraction**, never on a page view. Summaries are cached by `(document_id, updated_at)`.
- **Bedrock provisioned throughput.** It's billed per hour whether used or not. It's never used here; on-demand only.
- **Logs kept forever.** Log groups get 14-day retention.
- **NAT gateways or VPC endpoints.** The plan uses no VPC, so it has none of those hourly charges.
- **Forgotten resources.** Everything is created by one CloudFormation stack, and the teardown is a single command (section 8).

## 4. Where each adapter plugs in

| Seam | Today | AWS adapter | Switch |
|---|---|---|---|
| **File storage** | `settings.upload_dir` used directly in `app/uploads.py` and `app/api/documents.py` (process, file) | `S3DocumentStore` | `STORAGE_BACKEND=local\|s3`, `S3_BUCKET` |
| **OCR** | `OcrEngine.page_words(page)` in `app/extraction/ocr.py` | `TextractOcr` | `OCR_BACKEND=tesseract\|textract\|none` |
| **Field reading (optional)** | `RuleBasedFieldExtractor.extract_fields()` | `TextractExpenseFieldExtractor` | `FIELD_EXTRACTOR=rules\|textract_expense` |
| **Summary** | `AgentExplainer.explain()` in `app/agents/models.py` | `BedrockExplainer` | `EXPLAINER_MODE=mock\|bedrock`, `BEDROCK_MODEL_ID` |
| **Orchestration** | `process_document()` in `app/processing.py` | Step Functions state machine calling the same functions | `PIPELINE=inline\|stepfunctions` |
| **Observability** | Python `logging` (IDs and statuses only) | CloudWatch log group + metrics via Embedded Metric Format | `METRICS_BACKEND=none\|cloudwatch` |

Every switch defaults to the local value. `boto3` would go in an optional dependency group (`uv sync --group aws`) and be imported only inside adapters, so a local install doesn't change.

### Adapter notes

**S3DocumentStore**
- The bucket blocks all public access, has default encryption (SSE-S3), enforces TLS (`aws:SecureTransport`), and turns versioning off to keep costs down.
- Object key: `uploads/<document_id><ext>`, using the server-generated name only. Client file names are never used as keys.
- All upload checks (size, signature, structure) still run locally **before** the PUT.
- For extraction, the object is downloaded to a temporary file that's deleted in a `finally` block. The `/file` endpoint streams the object through the backend; S3 URLs are never exposed to the browser.

**TextractOcr**
- It implements the existing `page_words(page)`. The page is rendered to PNG with PyMuPDF and sent as bytes to synchronous `DetectDocumentText`. Each `WORD` block's bounding box (0–1 ratios) is scaled to page points, so the existing `build_lines()` and field rules work unchanged.
- One API call per page that has no text layer. Pages that already have text never go to Textract.
- Word confidence (0–100) would feed the `low_quality_scan` issue, which needs an OCR confidence that Tesseract isn't giving us yet.

**TextractExpenseFieldExtractor (optional, later)**
- Maps `AnalyzeExpense` `SummaryFields` (`VENDOR_NAME`, `INVOICE_RECEIPT_ID`, `INVOICE_RECEIPT_DATE`, `DUE_DATE`, `SUBTOTAL`, `TAX`, `TOTAL`, …) and `LineItemGroups` into `InvoiceFields`. Textract's confidence becomes the field confidence, and its geometry and page become the evidence.
- Its date and amount text still goes through **our** parsers, so ambiguous dates stay ambiguous. Validation stays deterministic and local.
- Only worth it if the comparison in section 7 shows it beats the rule-based extractor on the samples.

**BedrockExplainer**
- Uses the Bedrock `Converse` API with one call per document and no tools. The input is the same `ExplainerInput` the mock gets: fields, validation and corrections, but **not** the raw page text, which keeps tokens down and limits what leaves the machine. The model must return JSON matching `ExplanationDraft`.
- Runs through the existing `explain_document()`, so the guardrails and the mock fallback apply unchanged. `model_generated=true` shows "model: bedrock" in the UI.
- Results are cached per `(document_id, updated_at)`. There's a timeout (for example 20 s) and no automatic retry loop.
- Bedrock Guardrails (the AWS feature) is optional extra protection. It doesn't replace our own checks.

**Step Functions (optional, last)**
- A Standard workflow: `ExtractText` → `ReadFields` → `Validate` → `Explain` → `Save`. Each step is a small Lambda that imports this backend package. On failure, a `Catch` sets the status to `failed`.
- This needs the database to be reachable from Lambda. SQLite on a laptop isn't, so it would mean moving document records to DynamoDB or RDS, which is a separate, bigger decision. **I'd recommend not doing this step** unless the goal is specifically to learn Step Functions. If it is, a reduced version that only orchestrates Textract and S3 and returns results to the local backend avoids the database move.

**CloudWatch**
- One log group, `/docagent/backend`, with 14-day retention. The existing rule still holds: IDs, statuses and issue codes only, never document text or field values.
- Metrics (Embedded Metric Format, so no separate API calls): `DocumentsProcessed` by status, `ExtractionMethod`, `TextractPages`, `ExplainerFallbacks`, `BedrockTokens`.
- Alarms: failure rate over 20% in 1 hour, and any guardrail fallback. These are in addition to the Budgets alarm, not a replacement for it.

## 5. IAM: least privilege

The app's role or Identity Center permission set gets only this, with every resource scoped down. No `*` actions, and no `s3:*`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "UploadsOnly",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject"],
      "Resource": "arn:aws:s3:::<bucket>/uploads/*"
    },
    {
      "Sid": "OcrOnly",
      "Effect": "Allow",
      "Action": ["textract:DetectDocumentText", "textract:AnalyzeExpense"],
      "Resource": "*"
    },
    {
      "Sid": "OneModelOnly",
      "Effect": "Allow",
      "Action": ["bedrock:InvokeModel"],
      "Resource": "arn:aws:bedrock:<region>::foundation-model/<model-id>"
    },
    {
      "Sid": "OwnLogsOnly",
      "Effect": "Allow",
      "Action": ["logs:CreateLogStream", "logs:PutLogEvents"],
      "Resource": "arn:aws:logs:<region>:<account>:log-group:/docagent/backend:*"
    }
  ]
}
```

- Textract doesn't support resource-level permissions for these synchronous actions, so `Resource: "*"` is required there, but only for those two actions.
- There's **no `s3:DeleteObject`**. The app never deletes originals, which matches "never alter source PDFs". Teardown uses your admin session, not the app's role.
- The bucket policy denies any request that isn't over TLS.
- If an inference-profile model ID is used (for example `us.` prefixed), the profile ARN must be added to `OneModelOnly`.

## 6. Implementation steps, each needing your approval

| Step | What happens | Creates AWS resources? | Cost | Your approval needed |
|---|---|---|---|---|
| **1. Storage seam** | Add a `DocumentStore` interface with `LocalDocumentStore` and refactor the three `upload_dir` uses. Tests stay green. | No | $0 | Go-ahead to change code |
| **2. Adapters and stubbed tests** | Add an `aws` dependency group with `boto3`. Write `S3DocumentStore`, `TextractOcr` and `BedrockExplainer`, unit-tested with `botocore.stub.Stubber` (no network). | No | $0 | Go-ahead to change code |
| **3. Infrastructure template** | Write `infra/docagent.yaml` (CloudFormation: bucket, bucket policy, log group with retention, least-privilege managed policy). You review it. | No (file only) | $0 | Review |
| **4. Deploy the stack** | `aws cloudformation deploy` with your profile, after you've done section 2. | **Yes**: bucket, log group, policy | ≈ $0/month idle | **Explicit approval** |
| **5. Turn on Textract OCR** | `OCR_BACKEND=textract`. Process `inv09` and `inv11`, then compare with the ground truth. | No new resources; **paid API calls** | ≈ $0.003 for both scans | **Explicit approval** |
| **6. Turn on Bedrock** | Request model access, set `EXPLAINER_MODE=bedrock`, and run on the 14 samples. | No new resources; **paid API calls** | ≈ $0.10 | **Explicit approval** |
| **7. AnalyzeExpense comparison** | Run `FIELD_EXTRACTOR=textract_expense` on the 14 samples and score it against the ground truth. | **Paid API calls** | ≈ $0.14 | Optional, needs approval |
| **8. Step Functions** | Only if wanted (see section 4). | **Yes**: state machine, Lambdas | Pennies, but a bigger code change | Separate plan and approval |

Integration tests that call real AWS are marked `@pytest.mark.aws` and skipped unless `AWS_INTEGRATION=1`, so `uv run pytest` never costs money.

## 7. How we'd know it's worth it

Use the existing ground truth (`backend/sample_data/ground_truth/`):
- **OCR:** after step 5, `inv09_scanned` should reach `processed` with every field matching the ground truth. `inv11_low_quality_scan` should match on the key fields (vendor, number, dates, total), or be flagged `low_quality_scan` and `needs_review`. A wrong value that comes back marked high-confidence counts as a failure.
- **AnalyzeExpense:** count field-for-field matches across all 14 samples against the rule-based extractor's 13 of 13 text PDFs, and include the scans. It's only adopted if it does better without new false positives.
- **Bedrock:** zero guardrail fallbacks across the 14 samples, and a person agrees the summaries are clearer than the template ones.

## 8. Teardown

```bash
aws s3 rm s3://<bucket> --recursive --profile docagent
aws cloudformation delete-stack --stack-name docagent --profile docagent
```

After that, set `STORAGE_BACKEND=local`, `OCR_BACKEND=tesseract` and `EXPLAINER_MODE=mock`, and the app works exactly as it does today. Documents that were stored in S3 need to be copied back first; the plan includes an `export-from-s3` helper in step 2.

## 9. Recommendation

Do **steps 1–3** (all local and free), then **steps 4–5** to fix the one real gap: scanned invoices. Step 6 is optional polish. Skip step 8 unless learning Step Functions is a goal in itself.
