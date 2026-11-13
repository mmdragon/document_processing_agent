"use client";

import Link from "next/link";
import { useRef, useState } from "react";
import {
  ACCEPTED_EXTENSIONS,
  ApiError,
  api,
  MAX_UPLOAD_BYTES,
  type DocumentDetail,
} from "@/lib/api";
import { formatBytes } from "@/lib/format";
import StatusBadge from "./StatusBadge";

type Phase =
  | { kind: "idle" }
  | { kind: "working"; step: string }
  | { kind: "done"; doc: DocumentDetail }
  | { kind: "error"; message: string };

function checkFile(file: File): string | null {
  const name = file.name.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((ext) => name.endsWith(ext))) {
    return "Only PDF, PNG or JPEG files can be uploaded.";
  }
  if (file.size === 0) return "That file is empty.";
  if (file.size > MAX_UPLOAD_BYTES) {
    return `That file is ${formatBytes(file.size)}; the limit is ${formatBytes(MAX_UPLOAD_BYTES)}.`;
  }
  return null;
}

export default function UploadPanel({ onChange }: { onChange: () => void }) {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const busy = phase.kind === "working";

  async function handle(file: File | undefined) {
    if (!file || busy) return;
    const problem = checkFile(file);
    if (problem) {
      setPhase({ kind: "error", message: problem });
      return;
    }
    try {
      setPhase({ kind: "working", step: `Uploading ${file.name}…` });
      const uploaded = await api.upload(file);
      onChange();
      setPhase({ kind: "working", step: "Extracting and checking fields…" });
      const doc = await api.process(uploaded.document_id);
      setPhase({ kind: "done", doc });
    } catch (e) {
      setPhase({
        kind: "error",
        message: e instanceof ApiError ? e.message : "Something went wrong during upload.",
      });
    } finally {
      onChange();
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="text-base font-semibold text-gray-900">Upload an invoice</h2>
      <p className="mt-1 text-sm text-gray-600">
        PDF, PNG or JPEG up to {formatBytes(MAX_UPLOAD_BYTES)}. Use synthetic invoices only, for
        example from <code className="text-xs">backend/sample_data/invoices/</code>.
      </p>

      <label
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handle(e.dataTransfer.files?.[0]);
        }}
        className={`mt-4 flex cursor-pointer flex-col items-center justify-center rounded-md border-2 border-dashed px-4 py-8 text-center text-sm transition ${
          dragging ? "border-blue-500 bg-blue-50" : "border-gray-300 hover:border-gray-400"
        } ${busy ? "pointer-events-none opacity-60" : ""}`}
      >
        <span className="font-medium text-gray-800">Drop a file here or click to choose</span>
        <span className="mt-1 text-xs text-gray-500">It is processed as soon as it uploads.</span>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg"
          className="sr-only"
          disabled={busy}
          onChange={(e) => handle(e.target.files?.[0])}
        />
      </label>

      <div className="mt-3 min-h-6 text-sm" aria-live="polite">
        {phase.kind === "working" && (
          <p className="flex items-center gap-2 text-gray-700">
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-gray-400 border-t-transparent" />
            {phase.step}
          </p>
        )}
        {phase.kind === "error" && <p className="text-red-700">{phase.message}</p>}
        {phase.kind === "done" && (
          <p className="flex flex-wrap items-center gap-2 text-gray-800">
            <span>{phase.doc.original_filename}</span>
            <StatusBadge status={phase.doc.status} />
            <Link
              href={`/documents/${phase.doc.document_id}`}
              className="font-medium text-blue-700 underline-offset-2 hover:underline"
            >
              Open review →
            </Link>
          </p>
        )}
      </div>
    </section>
  );
}
