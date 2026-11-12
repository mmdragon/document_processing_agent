export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type Health = { status: string };

export async function getHealth(signal?: AbortSignal): Promise<Health> {
  const res = await fetch(`${API_BASE_URL}/api/health`, { signal, cache: "no-store" });
  if (!res.ok) throw new Error(`Health check failed: HTTP ${res.status}`);
  return res.json();
}
