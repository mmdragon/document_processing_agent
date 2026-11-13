"use client";

import { useState } from "react";
import { ApiError, type DocumentDetail } from "@/lib/api";
import { formatDateTime } from "@/lib/format";

type Props = {
  doc: DocumentDetail;
  onProcess: () => Promise<void>;
  onReview: (reviewed: boolean, note: string) => Promise<void>;
};

export default function ReviewActions({ doc, onProcess, onReview }: Props) {
  const [busy, setBusy] = useState<null | "process" | "review">(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const reviewed = doc.status === "reviewed";
  const canProcess = !reviewed && doc.status !== "processing";
  const canReview = ["processed", "needs_review", "needs_ocr"].includes(doc.status);
  const openIssues = (doc.validation?.issues ?? []).filter((i) => i.severity !== "info").length;

  async function run(kind: "process" | "review", fn: () => Promise<void>) {
    setBusy(kind);
    setError(null);
    try {
      await fn();
      setNote("");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Action failed.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="text-base font-semibold text-gray-900">Review</h2>

      {reviewed ? (
        <div className="mt-3 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-900">
          Marked reviewed {formatDateTime(doc.reviewed_at)}.
          {doc.review_note && <div className="mt-1 text-emerald-800">“{doc.review_note}”</div>}
        </div>
      ) : (
        <p className="mt-1 text-sm text-gray-600">
          Check the fields against the original, correct anything wrong, then mark it reviewed.
          {openIssues > 0 && (
            <span className="font-medium text-amber-800">
              {" "}
              {openIssues} open {openIssues === 1 ? "issue remains" : "issues remain"}.
            </span>
          )}
        </p>
      )}

      {canReview && (
        <input
          type="text"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Review note (optional)"
          maxLength={1000}
          className="mt-3 w-full rounded border border-gray-300 px-2 py-1.5 text-sm"
          aria-label="Review note"
        />
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {canReview && (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => run("review", () => onReview(true, note))}
            className="rounded bg-emerald-700 px-3 py-1.5 text-sm font-medium text-white hover:bg-emerald-800 disabled:opacity-50"
          >
            {busy === "review" ? "Saving…" : "Mark as reviewed"}
          </button>
        )}
        {reviewed && (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => run("review", () => onReview(false, ""))}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-800 hover:bg-gray-50 disabled:opacity-50"
          >
            {busy === "review" ? "Reopening…" : "Reopen for edits"}
          </button>
        )}
        {canProcess && (
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => run("process", onProcess)}
            className="rounded border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-800 hover:bg-gray-50 disabled:opacity-50"
          >
            {busy === "process"
              ? "Processing…"
              : doc.status === "uploaded"
                ? "Process document"
                : "Re-run extraction"}
          </button>
        )}
      </div>
      {error && <p className="mt-2 text-sm text-red-700">{error}</p>}
      <p className="mt-3 text-xs text-gray-500">
        Marking reviewed records that a person checked the data. It does not approve or schedule
        payment.
      </p>
    </section>
  );
}
