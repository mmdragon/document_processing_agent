import type { ValidationResult } from "@/lib/api";

const SEVERITY = {
  error: { label: "Error", className: "border-red-200 bg-red-50 text-red-900", dot: "bg-red-500" },
  warning: {
    label: "Warning",
    className: "border-amber-200 bg-amber-50 text-amber-900",
    dot: "bg-amber-500",
  },
  info: { label: "Note", className: "border-blue-200 bg-blue-50 text-blue-900", dot: "bg-blue-500" },
} as const;

const ORDER = { error: 0, warning: 1, info: 2 } as const;

const OUTCOME = {
  passed: { icon: "✓", className: "text-green-700" },
  failed: { icon: "✗", className: "text-red-700" },
  skipped: { icon: "–", className: "text-gray-400" },
} as const;

export default function ValidationPanel({ validation }: { validation: ValidationResult }) {
  const issues = [...validation.issues].sort((a, b) => ORDER[a.severity] - ORDER[b.severity]);
  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <h2 className="text-base font-semibold text-gray-900">Validation</h2>
      <p className="mt-1 text-xs text-gray-500">
        Deterministic rules run on the extracted values plus any corrections. Nothing here is
        model-generated.
      </p>

      {issues.length === 0 ? (
        <p className="mt-3 rounded-md border border-green-200 bg-green-50 px-3 py-2 text-sm text-green-900">
          No issues found.
        </p>
      ) : (
        <ul className="mt-3 space-y-2">
          {issues.map((issue, i) => {
            const s = SEVERITY[issue.severity];
            return (
              <li key={`${issue.code}-${i}`} className={`rounded-md border px-3 py-2 text-sm ${s.className}`}>
                <div className="flex items-start gap-2">
                  <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${s.dot}`} aria-hidden />
                  <div>
                    <span className="font-medium">{s.label}: </span>
                    {issue.message}
                    <div className="mt-0.5 font-mono text-[11px] opacity-70">{issue.code}</div>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      <h3 className="mt-5 text-sm font-semibold text-gray-800">Checks</h3>
      <ul className="mt-2 divide-y divide-gray-100 text-sm">
        {validation.checks.map((c) => (
          <li key={c.name} className="flex gap-2 py-2">
            <span
              className={`w-4 shrink-0 font-bold ${OUTCOME[c.outcome].className}`}
              aria-label={c.outcome}
            >
              {OUTCOME[c.outcome].icon}
            </span>
            <div>
              <div className="font-medium capitalize text-gray-800">
                {c.name.replaceAll("_", " ")}
              </div>
              <div className="text-xs text-gray-600">{c.detail}</div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
