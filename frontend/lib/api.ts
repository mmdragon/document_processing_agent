// Typed client for the FastAPI backend. Types mirror backend/app/schemas.

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const ACCEPTED_EXTENSIONS = [".pdf", ".png", ".jpg", ".jpeg"];

export type ProcessingStatus =
  | "uploaded"
  | "processing"
  | "processed"
  | "needs_review"
  | "needs_ocr"
  | "failed"
  | "reviewed";

export type DocumentSummary = {
  document_id: string;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  page_count: number;
  uploaded_at: string;
  updated_at: string;
  status: ProcessingStatus;
  extraction_method: "text" | "ocr" | "mixed" | "none" | null;
  error: string | null;
  reviewed_at: string | null;
};

export type Evidence = { page_number: number; line: string; method: "text" | "ocr" };

export type FieldStatus = "found" | "missing" | "ambiguous" | "unparseable";

export type ExtractedField = {
  value: string | null; // dates are ISO strings, money is a decimal string
  raw: string | null;
  status: FieldStatus;
  confidence: number;
  evidence: Evidence | null;
  note: string | null;
  corrected: boolean;
};

export type LineItem = {
  description: string;
  quantity: string;
  unit_price: string;
  amount: string;
  evidence: Evidence;
};

export const SCALAR_FIELDS = [
  "vendor_name",
  "vendor_address",
  "invoice_number",
  "invoice_date",
  "due_date",
  "currency",
  "purchase_order_number",
  "payment_terms",
  "subtotal",
  "discount",
  "tax",
  "shipping",
  "total",
] as const;
export type ScalarField = (typeof SCALAR_FIELDS)[number];

export type InvoiceFields = Record<ScalarField, ExtractedField> & {
  line_items: LineItem[];
  extraction_notes: string[];
};

export type ValidationIssue = {
  code: string;
  severity: "error" | "warning" | "info";
  field: string | null;
  message: string;
  details: Record<string, unknown>;
};

export type ValidationCheck = {
  name: string;
  outcome: "passed" | "failed" | "skipped";
  detail: string;
};

export type ValidationResult = {
  issues: ValidationIssue[];
  checks: ValidationCheck[];
  fields_needing_review: string[];
};

export type PageText = {
  page_number: number;
  text: string;
  char_count: number;
  method: "text" | "ocr" | "none";
  has_images: boolean;
};

export type ExtractionResult = {
  method: "text" | "ocr" | "mixed" | "none";
  page_count: number;
  pages: PageText[];
  warnings: string[];
  extractor: string;
  ocr_available: boolean;
};

export type Correction = {
  field: ScalarField;
  original_value: string | null;
  original_status: FieldStatus;
  corrected_value: string | null;
  note: string | null;
  corrected_at: string;
};

export type DocumentDetail = DocumentSummary & {
  extraction: ExtractionResult | null;
  fields: InvoiceFields | null;
  corrections: Correction[];
  validation: ValidationResult | null;
  review_note: string | null;
};

export type ExplanationItem = {
  kind: "fact" | "interpretation" | "question";
  text: string;
  refs: string[];
  evidence: Evidence[];
};

export type Explanation = {
  summary: string;
  sections: { title: string; items: ExplanationItem[] }[];
  questions: ExplanationItem[];
  next_steps: string[];
  explainer: string;
  model_generated: boolean;
  disclaimer: string;
  guardrails: { passed: boolean; violations: string[]; fallback_used: boolean };
  generated_at: string;
};

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
    public field?: string,
  ) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, { cache: "no-store", ...init });
  } catch {
    throw new ApiError(0, "Cannot reach the backend. Is it running on port 8000?");
  }
  if (res.ok) return res.json() as Promise<T>;

  let message = `Request failed (HTTP ${res.status}).`;
  let code: string | undefined;
  let field: string | undefined;
  try {
    const body = await res.json();
    const detail = body?.detail;
    if (typeof detail === "string") message = detail;
    else if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      message = detail.message ?? message;
      code = detail.code;
      field = detail.field;
    } else if (Array.isArray(detail) && detail[0]?.msg) {
      message = detail.map((d: { msg: string }) => d.msg).join("; ");
    }
  } catch {
    // keep the generic message
  }
  throw new ApiError(res.status, message, code, field);
}

const json = (body: unknown): RequestInit => ({
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const api = {
  health: () => request<{ status: string }>("/api/health"),
  list: () => request<DocumentSummary[]>("/api/documents"),
  get: (id: string) => request<DocumentDetail>(`/api/documents/${id}`),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<DocumentSummary>("/api/documents", { method: "POST", body: form });
  },
  process: (id: string) =>
    request<DocumentDetail>(`/api/documents/${id}/process`, { method: "POST" }),
  correct: (id: string, corrections: { field: ScalarField; value: string | null; note?: string }[]) =>
    request<DocumentDetail>(`/api/documents/${id}/corrections`, json({ corrections })),
  review: (id: string, reviewed: boolean, note?: string) =>
    request<DocumentDetail>(`/api/documents/${id}/review`, json({ reviewed, note: note || null })),
  explanation: (id: string) => request<Explanation>(`/api/documents/${id}/explanation`),
  fileUrl: (id: string) => `${API_BASE_URL}/api/documents/${id}/file`,
  reportUrl: (id: string, format: "json" | "markdown" = "markdown") =>
    `${API_BASE_URL}/api/documents/${id}/report?format=${format}`,
};
