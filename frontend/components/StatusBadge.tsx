import type { ProcessingStatus } from "@/lib/api";

const STYLES: Record<ProcessingStatus, { label: string; className: string }> = {
  uploaded: { label: "Uploaded", className: "bg-gray-100 text-gray-700 ring-gray-300" },
  processing: { label: "Processing", className: "bg-blue-50 text-blue-700 ring-blue-200" },
  processed: { label: "Checks passed", className: "bg-green-50 text-green-800 ring-green-200" },
  needs_review: { label: "Needs review", className: "bg-amber-50 text-amber-800 ring-amber-300" },
  needs_ocr: { label: "Needs OCR", className: "bg-purple-50 text-purple-800 ring-purple-200" },
  failed: { label: "Failed", className: "bg-red-50 text-red-700 ring-red-200" },
  reviewed: { label: "Reviewed", className: "bg-emerald-600 text-white ring-emerald-700" },
};

export default function StatusBadge({ status }: { status: ProcessingStatus }) {
  const s = STYLES[status] ?? STYLES.uploaded;
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${s.className}`}
    >
      {s.label}
    </span>
  );
}
