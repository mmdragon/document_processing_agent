"use client";

import { useEffect, useState } from "react";
import { getHealth } from "@/lib/api";

type State = "checking" | "ok" | "down";

export default function HealthStatus() {
  const [state, setState] = useState<State>("checking");

  useEffect(() => {
    const ctrl = new AbortController();
    getHealth(ctrl.signal)
      .then((h) => setState(h.status === "ok" ? "ok" : "down"))
      .catch((e) => {
        if (!ctrl.signal.aborted) setState("down");
        if (e?.name !== "AbortError") console.warn(e);
      });
    return () => ctrl.abort();
  }, []);

  const styles: Record<State, string> = {
    checking: "bg-gray-100 text-gray-700",
    ok: "bg-green-100 text-green-800",
    down: "bg-red-100 text-red-800",
  };
  const labels: Record<State, string> = {
    checking: "Checking backend…",
    ok: "Backend connected",
    down: "Backend unreachable — is uvicorn running on port 8000?",
  };

  return (
    <span className={`inline-block rounded px-3 py-1 text-sm ${styles[state]}`}>
      {labels[state]}
    </span>
  );
}
