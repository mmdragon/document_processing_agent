"use client";

import { useState } from "react";
import DocumentList from "@/components/DocumentList";
import UploadPanel from "@/components/UploadPanel";

export default function Home() {
  const [refreshKey, setRefreshKey] = useState(0);
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-gray-900">Invoice review</h1>
        <p className="mt-1 text-sm text-gray-600">
          Upload an invoice to extract its fields and run arithmetic, required-field and
          duplicate checks. Anything uncertain is flagged for a person to review.
        </p>
      </div>
      <UploadPanel onChange={() => setRefreshKey((k) => k + 1)} />
      <DocumentList refreshKey={refreshKey} />
    </div>
  );
}
