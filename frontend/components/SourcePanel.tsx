"use client";

import { useState } from "react";
import { api, type DocumentDetail } from "@/lib/api";

export default function SourcePanel({ doc }: { doc: DocumentDetail }) {
  const [showOriginal, setShowOriginal] = useState(false);
  const pages = doc.extraction?.pages ?? [];
  const url = api.fileUrl(doc.document_id);

  return (
    <section className="rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-200 px-5 py-3">
        <h2 className="text-base font-semibold text-gray-900">Source</h2>
        <div className="flex gap-3 text-sm">
          <button
            type="button"
            onClick={() => setShowOriginal((s) => !s)}
            className="font-medium text-blue-700 hover:underline"
          >
            {showOriginal ? "Hide original" : "Show original"}
          </button>
          <a href={url} target="_blank" rel="noreferrer" className="text-blue-700 hover:underline">
            Open in new tab ↗
          </a>
        </div>
      </div>

      {showOriginal &&
        (doc.content_type === "application/pdf" ? (
          <iframe
            src={url}
            title={`Original ${doc.original_filename}`}
            className="h-[640px] w-full border-b border-gray-200"
          />
        ) : (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt={`Original ${doc.original_filename}`} className="mx-auto max-h-[640px]" />
        ))}

      {doc.extraction?.warnings.length ? (
        <ul className="border-b border-gray-100 px-5 py-3 text-xs text-amber-800">
          {doc.extraction.warnings.map((w, i) => (
            <li key={i}>{w}</li>
          ))}
        </ul>
      ) : null}

      {pages.length === 0 ? (
        <p className="px-5 py-4 text-sm text-gray-600">No extracted text yet.</p>
      ) : (
        <div className="divide-y divide-gray-100">
          {pages.map((p) => (
            <details key={p.page_number} className="px-5 py-3">
              <summary className="cursor-pointer text-sm text-gray-700">
                Page {p.page_number} · {p.method === "none" ? "no text" : `${p.char_count} characters via ${p.method}`}
              </summary>
              <pre className="mt-2 max-h-96 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-3 text-xs text-gray-800">
                {p.text || "(empty)"}
              </pre>
            </details>
          ))}
        </div>
      )}
      {doc.extraction && (
        <p className="border-t border-gray-100 px-5 py-2 text-[11px] text-gray-400">
          {doc.extraction.extractor} · OCR {doc.extraction.ocr_available ? "available" : "not installed"}
        </p>
      )}
    </section>
  );
}
