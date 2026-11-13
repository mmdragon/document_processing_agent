"use client";

import { useState } from "react";
import {
  ApiError,
  SCALAR_FIELDS,
  type Correction,
  type DocumentDetail,
  type ExtractedField,
  type ScalarField,
} from "@/lib/api";
import {
  DATE_FIELDS,
  FIELD_LABELS,
  MONEY_FIELDS,
  effectiveValue,
  formatFieldValue,
  latestCorrections,
} from "@/lib/format";

type Props = {
  doc: DocumentDetail;
  editable: boolean;
  onCorrect: (field: ScalarField, value: string | null, note: string) => Promise<void>;
};

export default function FieldsTable({ doc, editable, onCorrect }: Props) {
  const fields = doc.fields!;
  const latest = latestCorrections(doc.corrections);
  const review = new Set(doc.validation?.fields_needing_review ?? []);
  const currency = effectiveValue(fields.currency, latest.currency);
  const noText = doc.extraction_method === "none";

  return (
    <section className="rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="border-b border-gray-200 px-5 py-3">
        <h2 className="text-base font-semibold text-gray-900">Extracted fields</h2>
        <p className="mt-1 text-xs text-gray-500">
          Each value shows the line it was read from. Corrections are kept beside the extracted
          value; the original is never overwritten.
        </p>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
            <tr>
              <th className="px-3 py-2 font-medium sm:px-5">Field</th>
              <th className="px-3 py-2 font-medium sm:px-5">Value</th>
              <th className="hidden px-5 py-2 font-medium sm:table-cell">Evidence</th>
              {editable && <th className="px-3 py-2 font-medium sm:px-5" />}
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {SCALAR_FIELDS.map((name) => (
              <FieldRow
                key={name}
                name={name}
                field={fields[name]}
                correction={latest[name]}
                flagged={review.has(name)}
                currency={currency}
                noText={noText}
                editable={editable}
                onCorrect={onCorrect}
              />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function StatusTag({
  field,
  flagged,
  noText,
}: {
  field: ExtractedField;
  flagged: boolean;
  noText: boolean;
}) {
  if (field.status === "missing")
    return (
      <span className="text-xs text-gray-500">{noText ? "not read (no text)" : "not on document"}</span>
    );
  if (field.status === "ambiguous")
    return <span className="text-xs font-medium text-amber-800">ambiguous</span>;
  if (field.status === "unparseable")
    return <span className="text-xs font-medium text-amber-800">unreadable</span>;
  const pct = Math.round(field.confidence * 100);
  return (
    <span className={`text-xs ${flagged ? "font-medium text-amber-800" : "text-gray-500"}`}>
      {pct}% confidence{flagged ? " · check" : ""}
    </span>
  );
}

function EvidenceLine({ field }: { field: ExtractedField }) {
  if (!field.evidence) return <span className="text-gray-400">—</span>;
  return (
    <>
      <span className="font-medium text-gray-500">
        p.{field.evidence.page_number}
        {field.evidence.method === "ocr" ? " (OCR)" : ""}:{" "}
      </span>
      <code className="whitespace-pre-wrap break-words rounded bg-gray-100 px-1 py-0.5">
        {field.evidence.line}
      </code>
    </>
  );
}

function FieldRow({
  name,
  field,
  correction,
  flagged,
  currency,
  noText,
  editable,
  onCorrect,
}: {
  name: ScalarField;
  field: ExtractedField;
  correction?: Correction;
  flagged: boolean;
  currency: string | null;
  noText: boolean;
  editable: boolean;
  onCorrect: Props["onCorrect"];
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const current = effectiveValue(field, correction);
  const extractedDisplay =
    field.value !== null ? formatFieldValue(name, field.value, currency) : (field.raw ?? "—");

  function startEdit() {
    setValue(current ?? "");
    setNote("");
    setError(null);
    setEditing(true);
  }

  async function save() {
    setSaving(true);
    setError(null);
    try {
      await onCorrect(name, value.trim() === "" ? null : value.trim(), note.trim());
      setEditing(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Could not save the correction.");
    } finally {
      setSaving(false);
    }
  }

  const highlight = (flagged || field.status === "ambiguous") && !correction;
  const inputType = DATE_FIELDS.includes(name) ? "date" : "text";

  return (
    <tr className={highlight ? "bg-amber-50/60" : undefined}>
      <td className="px-3 py-2.5 align-top font-medium text-gray-700 sm:whitespace-nowrap sm:px-5">
        {FIELD_LABELS[name]}
      </td>
      <td className="px-3 py-2.5 align-top sm:px-5">
        {correction ? (
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-gray-900">
                {formatFieldValue(name, correction.corrected_value, currency)}
              </span>
              <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[11px] font-medium text-indigo-800">
                corrected
              </span>
            </div>
            <div className="mt-0.5 text-xs text-gray-500">
              Extracted: <span className="line-through">{extractedDisplay}</span>
              {correction.note && <> · “{correction.note}”</>}
            </div>
          </div>
        ) : (
          <div>
            <div className={field.value === null ? "text-gray-400" : "text-gray-900"}>
              {field.value !== null
                ? formatFieldValue(name, field.value, currency)
                : field.raw
                  ? `“${field.raw}”`
                  : "—"}
            </div>
            <StatusTag field={field} flagged={flagged} noText={noText} />
            {field.note && field.status !== "found" && (
              <div className="mt-0.5 text-xs text-amber-800">{field.note}</div>
            )}
          </div>
        )}

        <div className="mt-1 text-xs text-gray-600 sm:hidden">
          <EvidenceLine field={field} />
        </div>

        {editing && (
          <div className="mt-2 space-y-2 rounded-md border border-gray-200 bg-white p-3">
            <input
              type={inputType}
              inputMode={MONEY_FIELDS.includes(name) ? "decimal" : undefined}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder={
                MONEY_FIELDS.includes(name)
                  ? "e.g. 1234.50"
                  : name === "currency"
                    ? "e.g. USD"
                    : "Leave empty to clear"
              }
              maxLength={name === "currency" ? 3 : 500}
              className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
              aria-label={`Corrected ${FIELD_LABELS[name]}`}
            />
            <input
              type="text"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Reason (optional), e.g. checked against PDF"
              maxLength={500}
              className="w-full rounded border border-gray-300 px-2 py-1 text-sm"
              aria-label="Reason for correction"
            />
            {error && <p className="text-xs text-red-700">{error}</p>}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={save}
                disabled={saving}
                className="rounded bg-gray-900 px-3 py-1 text-xs font-medium text-white disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save correction"}
              </button>
              <button
                type="button"
                onClick={() => setEditing(false)}
                disabled={saving}
                className="rounded px-3 py-1 text-xs text-gray-700 hover:bg-gray-100"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </td>
      <td className="hidden max-w-md px-5 py-2.5 align-top text-xs text-gray-600 sm:table-cell">
        <EvidenceLine field={field} />
      </td>
      {editable && (
        <td className="px-3 py-2.5 text-right align-top sm:px-5">
          {!editing && (
            <button
              type="button"
              onClick={startEdit}
              className="text-xs font-medium text-blue-700 hover:underline"
            >
              {current === null ? "Add" : "Correct"}
            </button>
          )}
        </td>
      )}
    </tr>
  );
}
