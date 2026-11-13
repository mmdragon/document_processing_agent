"use client";

import { useEffect, useState } from "react";
import { ApiError, api, type DocumentDetail, type Explanation } from "@/lib/api";

const KIND = {
  fact: { label: "Fact", className: "bg-gray-100 text-gray-700" },
  interpretation: { label: "Interpretation", className: "bg-sky-100 text-sky-800" },
  question: { label: "Question", className: "bg-amber-100 text-amber-900" },
} as const;

type State =
  | { kind: "loading" }
  | { kind: "error"; message: string }
  | { kind: "ready"; explanation: Explanation };

export default function ExplanationPanel({ doc }: { doc: DocumentDetail }) {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [showFacts, setShowFacts] = useState(false);

  // Re-fetch whenever the document changes (processing, corrections, review).
  useEffect(() => {
    let cancelled = false;
    setState({ kind: "loading" });
    api
      .explanation(doc.document_id)
      .then((explanation) => !cancelled && setState({ kind: "ready", explanation }))
      .catch(
        (e) =>
          !cancelled &&
          setState({
            kind: "error",
            message: e instanceof ApiError ? e.message : "Could not load the summary.",
          }),
      );
    return () => {
      cancelled = true;
    };
  }, [doc.document_id, doc.updated_at]);

  const canReport = doc.fields !== null && doc.validation !== null;

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <h2 className="text-base font-semibold text-gray-900">Summary</h2>
        {state.kind === "ready" && (
          <span
            className="shrink-0 rounded bg-gray-100 px-1.5 py-0.5 text-[11px] text-gray-600"
            title={state.explanation.model_generated ? "Written by a language model" : "Written by fixed templates; no model involved"}
          >
            {state.explanation.model_generated
              ? `model: ${state.explanation.explainer}`
              : "template-based · no AI model"}
          </span>
        )}
      </div>

      {state.kind === "loading" && (
        <div className="mt-3 space-y-2" aria-busy="true">
          <div className="h-4 animate-pulse rounded bg-gray-100" />
          <div className="h-4 w-2/3 animate-pulse rounded bg-gray-100" />
        </div>
      )}
      {state.kind === "error" && <p className="mt-2 text-sm text-red-700">{state.message}</p>}

      {state.kind === "ready" && (
        <ExplanationBody
          e={state.explanation}
          showFacts={showFacts}
          onToggleFacts={() => setShowFacts((s) => !s)}
        />
      )}

      {canReport && (
        <a
          href={api.reportUrl(doc.document_id, "markdown")}
          className="mt-4 inline-block rounded border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-800 hover:bg-gray-50"
        >
          Download review report (.md)
        </a>
      )}
    </section>
  );
}

function ExplanationBody({
  e,
  showFacts,
  onToggleFacts,
}: {
  e: Explanation;
  showFacts: boolean;
  onToggleFacts: () => void;
}) {
  const facts = e.sections.flatMap((s) => s.items.filter((i) => i.kind === "fact"));
  const interpretations = e.sections.flatMap((s) =>
    s.items.filter((i) => i.kind === "interpretation"),
  );

  return (
    <div className="mt-2 space-y-3 text-sm">
      <p className="text-gray-800">{e.summary}</p>

      {e.guardrails.fallback_used && (
        <p className="rounded border border-amber-200 bg-amber-50 px-2 py-1 text-xs text-amber-900">
          The configured explainer&apos;s output failed safety checks, so this template summary
          is shown instead.
        </p>
      )}

      {e.questions.length > 0 && (
        <List title="Questions for you" items={e.questions} />
      )}
      {interpretations.length > 0 && (
        <List title="What this might mean" items={interpretations} />
      )}

      {e.next_steps.length > 0 && (
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">
            Suggested next steps
          </h3>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-gray-700">
            {e.next_steps.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ul>
        </div>
      )}

      {facts.length > 0 && (
        <div>
          <button
            type="button"
            onClick={onToggleFacts}
            className="text-xs font-medium text-blue-700 hover:underline"
            aria-expanded={showFacts}
          >
            {showFacts ? "Hide" : "Show"} the {facts.length} facts this is based on
          </button>
          {showFacts && <List items={facts} />}
        </div>
      )}

      <p className="border-t border-gray-100 pt-2 text-xs text-gray-500">{e.disclaimer}</p>
    </div>
  );
}

function List({ title, items }: { title?: string; items: Explanation["questions"] }) {
  return (
    <div>
      {title && (
        <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-500">{title}</h3>
      )}
      <ul className="mt-1 space-y-1.5">
        {items.map((item, i) => (
          <li key={i} className="flex gap-2">
            <span
              className={`mt-0.5 h-fit shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase ${KIND[item.kind].className}`}
            >
              {KIND[item.kind].label}
            </span>
            <span className="text-gray-700">{item.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
