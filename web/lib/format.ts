import type { CaseState, WaitingOn } from "./types";

export function ago(iso: string, now: number = Date.now()): string {
  const s = Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h`;
  return `${Math.round(h / 24)} d`;
}

export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export const STATE: Record<CaseState, { label: string; customer: string; tone: Tone }> = {
  agent_working: { label: "Agent working", customer: "Hipstraw is working on it", tone: "brand" },
  waiting_review: { label: "In review", customer: "With a Hipstraw reviewer", tone: "amber" },
  approved: { label: "Approved", customer: "Plan approved: ready to run", tone: "emerald" },
  returned: { label: "Returned", customer: "Returned to you: see the note", tone: "rose" },
};

export const WAITING: Record<WaitingOn, { label: string; tone: Tone }> = {
  agent: { label: "The agent", tone: "brand" },
  reviewer: { label: "You: approve the plan", tone: "amber" },
  customer: { label: "The customer", tone: "sky" },
  people: { label: "Executors: run the Moves", tone: "emerald" },
};

export type Tone = "brand" | "amber" | "emerald" | "rose" | "sky" | "slate";

export const TONE: Record<Tone, { chip: string; dot: string; text: string }> = {
  brand: { chip: "bg-indigo-50 text-indigo-700 ring-indigo-200", dot: "bg-indigo-500", text: "text-indigo-700" },
  amber: { chip: "bg-amber-50 text-amber-800 ring-amber-200", dot: "bg-amber-500", text: "text-amber-700" },
  emerald: { chip: "bg-emerald-50 text-emerald-700 ring-emerald-200", dot: "bg-emerald-500", text: "text-emerald-700" },
  rose: { chip: "bg-rose-50 text-rose-700 ring-rose-200", dot: "bg-rose-500", text: "text-rose-700" },
  sky: { chip: "bg-sky-50 text-sky-700 ring-sky-200", dot: "bg-sky-500", text: "text-sky-700" },
  slate: { chip: "bg-slate-100 text-slate-600 ring-slate-200", dot: "bg-slate-400", text: "text-slate-600" },
};

export const RUBRIC_TONE: Record<string, Tone> = {
  met: "emerald", partly: "sky", not_met: "rose", unknown: "slate", not_applicable: "slate",
  failed: "rose", not_confirmed: "amber",
};

export const EFFECT: Record<string, { label: string; tone: Tone }> = {
  E0: { label: "Internal", tone: "slate" },
  E1: { label: "Reads sources", tone: "sky" },
  E2: { label: "Model inference", tone: "brand" },
  E3: { label: "Contacts people", tone: "amber" },
};

export const words = (s: string) => s.replace(/_/g, " ");
export const plural = (n: number, noun: string, many = `${noun}s`) => `${n} ${n === 1 ? noun : many}`;
export const short = (hash: string | null | undefined, n = 10) => (hash ? hash.slice(0, n) : "");
