import type { CaseDetail, CaseSummary, LedgerEvent, LedgerView, Library, Offering } from "./types";

// No sign-in in this MVP: each workspace names its acting person and role on every change, and the desk API's
// authority gate checks the role (a customer may submit, only a reviewer may approve or return a plan).
export const REVIEWER = { actor: "Hipstraw reviewer", role: "reviewer" } as const;
export const CUSTOMER = { actor: "Customer team", role: "customer" } as const;

type Who = { actor: string; role: string };

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(path: string, init?: RequestInit & { who?: Who }): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (init?.who) {
    headers["X-Hipstraw-Actor"] = init.who.actor;
    headers["X-Hipstraw-Role"] = init.who.role;
  }
  const res = await fetch(path, { ...init, headers, cache: "no-store" });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new ApiError(res.status, (body as { detail?: string }).detail ?? `${res.status} ${res.statusText}`);
  return body as T;
}

export const api = {
  cases: () => call<CaseSummary[]>("/api/cases"),
  case: (id: string) => call<CaseDetail>(`/api/cases/${encodeURIComponent(id)}`),
  events: (id: string, after: number) => call<LedgerEvent[]>(`/api/cases/${encodeURIComponent(id)}/events?after=${after}`),
  library: () => call<Library>("/api/library"),
  ledger: () => call<LedgerView>("/api/ledger"),
  offerings: () => call<Offering[]>("/api/offerings"),
  submit: (body: unknown, who: Who) =>
    call<CaseSummary>("/api/requests", { method: "POST", body: JSON.stringify(body), who }),
  decide: (id: string, body: { action: "approve" | "return"; payloadHash: string; note: string }) =>
    call<CaseDetail>(`/api/cases/${encodeURIComponent(id)}/decision`, { method: "POST", body: JSON.stringify(body), who: REVIEWER }),
};
