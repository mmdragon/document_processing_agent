"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type DocumentSummary } from "@/lib/api";
import { formatBytes, formatDateTime } from "@/lib/format";
import StatusBadge from "./StatusBadge";

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; docs: DocumentSummary[] };

export default function DocumentList({ refreshKey }: { refreshKey: number }) {
  const [state, setState] = useState<State>({ kind: "loading" });

  const load = useCallback(async () => {
    try {
      const docs = await api.list();
      setState({ kind: "ready", docs });
    } catch (e) {
      setState({
        kind: "error",
        message: e instanceof ApiError ? e.message : "Could not load documents.",
      });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  return (
    <section className="rounded-lg border border-gray-200 bg-white shadow-sm">
      <div className="flex items-center justify-between border-b border-gray-200 px-5 py-3">
        <h2 className="text-base font-semibold text-gray-900">Documents</h2>
        <button
          type="button"
          onClick={() => {
            setState({ kind: "loading" });
            load();
          }}
          className="text-sm text-blue-700 hover:underline"
        >
          Refresh
        </button>
      </div>

      {state.kind === "loading" && (
        <div className="space-y-2 p-5" aria-busy="true">
          {[0, 1, 2].map((i) => (
            <div key={i} className="h-8 animate-pulse rounded bg-gray-100" />
          ))}
        </div>
      )}

      {state.kind === "error" && (
        <div className="p-5 text-sm">
          <p className="text-red-700">{state.message}</p>
          <p className="mt-1 text-gray-600">
            Start the backend with{" "}
            <code className="text-xs">uv run uvicorn app.main:app --reload --port 8000</code>{" "}
            in <code className="text-xs">backend/</code>, then refresh.
          </p>
        </div>
      )}

      {state.kind === "ready" && state.docs.length === 0 && (
        <p className="p-5 text-sm text-gray-600">
          No documents yet. Upload a synthetic invoice to get started.
        </p>
      )}

      {state.kind === "ready" && state.docs.length > 0 && (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50 text-left text-xs uppercase tracking-wide text-gray-500">
              <tr>
                <th className="px-5 py-2 font-medium">File</th>
                <th className="px-5 py-2 font-medium">Status</th>
                <th className="px-5 py-2 font-medium">Text from</th>
                <th className="px-5 py-2 font-medium">Pages</th>
                <th className="px-5 py-2 font-medium">Size</th>
                <th className="px-5 py-2 font-medium">Uploaded</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {state.docs.map((d) => (
                <tr key={d.document_id} className="hover:bg-gray-50">
                  <td className="px-5 py-2">
                    <Link
                      href={`/documents/${d.document_id}`}
                      className="font-medium text-blue-700 hover:underline"
                    >
                      {d.original_filename}
                    </Link>
                  </td>
                  <td className="px-5 py-2">
                    <StatusBadge status={d.status} />
                  </td>
                  <td className="px-5 py-2 text-gray-600">{d.extraction_method ?? "—"}</td>
                  <td className="px-5 py-2 text-gray-600">{d.page_count}</td>
                  <td className="px-5 py-2 text-gray-600">{formatBytes(d.size_bytes)}</td>
                  <td className="px-5 py-2 text-gray-600">{formatDateTime(d.uploaded_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
