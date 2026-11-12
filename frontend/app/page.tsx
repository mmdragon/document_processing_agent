import HealthStatus from "@/components/HealthStatus";

export default function Home() {
  return (
    <main className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="text-2xl font-semibold">Document Processing Agent</h1>
      <p className="mt-2 text-gray-600">
        Local-first invoice extraction and validation. Use synthetic invoices only. This tool
        never approves or sends payments.
      </p>
      <div className="mt-6">
        <HealthStatus />
      </div>
      <p className="mt-8 text-sm text-gray-500">
        Upload, review, and reports arrive in later phases.
      </p>
    </main>
  );
}
