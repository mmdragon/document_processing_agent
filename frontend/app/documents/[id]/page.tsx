"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import FieldsTable from "@/components/FieldsTable";
import LineItemsTable from "@/components/LineItemsTable";
import ReviewActions from "@/components/ReviewActions";
import SourcePanel from "@/components/SourcePanel";
import StatusBadge from "@/components/StatusBadge";
import ValidationPanel from "@/components/ValidationPanel";
import { ApiError, api, type DocumentDetail, type ScalarField } from "@/lib/api";
import { effectiveValue, formatBytes, formatDateTime, latestCorrections } from "@/lib/format";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string; notFound: boolean }
  | { kind: "ready"; doc: DocumentDetail };

export default function DocumentPage() {
  const { id } = useParams<{ id: string }>();
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      setState({ kind: "ready", doc: await api.get(id) });
    } catch (e) {
      setState({
        kind: "error",
        message: e instanceof ApiError ? e.message : "Could not load the document.",
        notFound: e instanceof ApiError && (e.status === 404 || e.status === 422),
      });
    }
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  if (state.kind === "loading") {
    return (
      <div className="space-y-4" aria-busy="true">
        <div className="h-8 w-1/3 animate-pulse rounded bg-gray-200" />
        <div className="h-40 animate-pulse rounded-lg bg-gray-100" />
        <div className="h-72 animate-pulse rounded-lg bg-gray-100" />
      </div>
    );
  }

  if (state.kind === "error") {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-5 text-sm text-red-900">
        <p className="font-medium">{state.notFound ? "Document not found." : state.message}</p>
        <div className="mt-3 flex gap-4">
          <Link href="/" className="text-blue-700 hover:underline">
            ← Back to documents
          </Link>
          {!state.notFound && (
            <button type="button" onClick={load} className="text-blue-700 hover:underline">
              Retry
            </button>
          )}
        </div>
      </div>
    );
  }

  const doc = state.doc;
  const setDoc = (d: DocumentDetail) => setState({ kind: "ready", doc: d });
  const editable = doc.fields !== null && !["reviewed", "processing"].includes(doc.status);
  const currency = doc.fields
    ? effectiveValue(doc.fields.currency, latestCorrections(doc.corrections).currency)
    : null;

  async function onCorrect(field: ScalarField, value: string | null, note: string) {
    setDoc(await api.correct(doc.document_id, [{ field, value, note: note || undefined }]));
  }

  return (
    <div className="space-y-6">
      <div>
        <Link href="/" className="text-sm text-blue-700 hover:underline">
          ← All documents
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-3">
          <h1 className="break-all text-2xl font-semibold text-gray-900">{doc.original_filename}</h1>
          <StatusBadge status={doc.status} />
        </div>
        <p className="mt-1 text-xs text-gray-500">
          Uploaded {formatDateTime(doc.uploaded_at)} · {formatBytes(doc.size_bytes)} ·{" "}
          {doc.page_count} page{doc.page_count === 1 ? "" : "s"}
          {doc.extraction_method && <> · text from {doc.extraction_method}</>}
        </p>
      </div>

      {doc.status === "failed" && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900">
          Processing failed: {doc.error ?? "unknown error"}. You can try re-running extraction.
        </div>
      )}
      {doc.status === "needs_ocr" && (
        <div className="rounded-md border border-purple-200 bg-purple-50 px-4 py-3 text-sm text-purple-900">
          This document has no text layer. Install Tesseract (<code>brew install tesseract</code>),
          restart the backend and re-run extraction, or enter the key fields by hand below.
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="min-w-0 space-y-6 lg:col-span-2">
          {doc.fields && <FieldsTable doc={doc} editable={editable} onCorrect={onCorrect} />}
          {doc.fields && <LineItemsTable fields={doc.fields} currency={currency} />}
          {doc.status === "uploaded" && (
            <p className="rounded-lg border border-gray-200 bg-white p-5 text-sm text-gray-600">
              This document has not been processed yet.
            </p>
          )}
          <SourcePanel doc={doc} />
        </div>
        <div className="min-w-0 space-y-6">
          <ReviewActions
            doc={doc}
            onProcess={async () => setDoc(await api.process(doc.document_id))}
            onReview={async (reviewed, note) =>
              setDoc(await api.review(doc.document_id, reviewed, note))
            }
          />
          {doc.validation && <ValidationPanel validation={doc.validation} />}
          {doc.corrections.length > 0 && (
            <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
              <h2 className="text-base font-semibold text-gray-900">Correction history</h2>
              <ul className="mt-2 space-y-2 text-xs text-gray-700">
                {[...doc.corrections].reverse().map((c, i) => (
                  <li key={i} className="border-l-2 border-indigo-200 pl-2">
                    <span className="font-medium">{c.field.replaceAll("_", " ")}</span>:{" "}
                    {c.original_value ?? "—"} → {c.corrected_value ?? "(cleared)"}
                    <div className="text-gray-500">
                      {formatDateTime(c.corrected_at)}
                      {c.note && <> · “{c.note}”</>}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}
