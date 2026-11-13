import type { Correction, ExtractedField, ScalarField } from "./api";

export const FIELD_LABELS: Record<ScalarField, string> = {
  vendor_name: "Vendor name",
  vendor_address: "Vendor address",
  invoice_number: "Invoice number",
  invoice_date: "Invoice date",
  due_date: "Due date",
  currency: "Currency",
  purchase_order_number: "PO number",
  payment_terms: "Payment terms",
  subtotal: "Subtotal",
  discount: "Discount",
  tax: "Tax",
  shipping: "Shipping",
  total: "Total",
};

export const DATE_FIELDS: ScalarField[] = ["invoice_date", "due_date"];
export const MONEY_FIELDS: ScalarField[] = ["subtotal", "discount", "tax", "shipping", "total"];

export function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatDateTime(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? iso
    : d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function formatMoney(value: string | null, currency: string | null): string {
  if (value === null) return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return value;
  const amount = n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  return currency ? `${amount} ${currency}` : amount;
}

export function formatFieldValue(
  field: ScalarField,
  value: string | null,
  currency: string | null,
): string {
  if (value === null || value === "") return "—";
  if (MONEY_FIELDS.includes(field)) return formatMoney(value, currency);
  return value;
}

/** The latest correction for each field (corrections are an append-only audit list). */
export function latestCorrections(corrections: Correction[]): Partial<Record<ScalarField, Correction>> {
  const out: Partial<Record<ScalarField, Correction>> = {};
  for (const c of corrections) out[c.field] = c;
  return out;
}

export function effectiveValue(field: ExtractedField, correction?: Correction): string | null {
  return correction ? correction.corrected_value : field.value;
}
