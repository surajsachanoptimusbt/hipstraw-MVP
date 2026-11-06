"use client";

import { motion } from "motion/react";
import { Info } from "lucide-react";
import { RUBRIC_TONE, words } from "@/lib/format";
import type { EvidenceView, Finding, Metric } from "@/lib/types";
import { Chip, CountUp, cx } from "./ui";

function groups<T extends { dimension: string }>(items: T[]): [string, T[]][] {
  const out = new Map<string, T[]>();
  for (const i of items) out.set(i.dimension, [...(out.get(i.dimension) ?? []), i]);
  return [...out.entries()];
}

/** Each metric against its target, by demand dimension. Never added up: the rubric's rules decide. */
export function Metrics({ metrics }: { metrics: Metric[] }) {
  const empty = metrics.every((m) => m.current === 0);
  return (
    <div className="space-y-5">
      {empty && (
        <div className="flex gap-3 rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 text-[12.5px] text-sky-900">
          <Info size={16} className="mt-0.5 shrink-0" />
          <p>All metrics are 0 because no evidence from the target buyers is recorded yet. Desk research never counts as
            demand; the metrics rise as the Moves run (the account map, interviews, pilots) and their evidence is recorded.</p>
        </div>
      )}
      {groups(metrics).map(([dim, ms]) => (
        <div key={dim}>
          <div className="mb-2 text-[12px] font-semibold uppercase tracking-wider text-slate-400">{dim}</div>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {ms.map((m, i) => {
              const na = m.state === "not_applicable";
              const pct = na || !m.target ? 0 : Math.min(100, (100 * m.current) / m.target);
              return (
                <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.04 * i }}
                  className={cx("rounded-xl border border-slate-200 bg-white p-3.5", na && "opacity-60")}>
                  <div className="text-[12.5px] font-medium text-slate-600">{m.label}</div>
                  <div className="mt-1 flex items-baseline gap-1.5">
                    {na ? <span className="text-2xl font-bold text-slate-400">n/a</span> : (
                      <><CountUp value={m.current} className="text-2xl font-bold tabular-nums text-slate-900" />
                        <span className="text-sm text-slate-400">/ {m.target}</span></>
                    )}
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-100">
                    <motion.div className="brand-gradient h-full rounded-full" initial={{ width: 0 }} animate={{ width: `${Math.max(pct, 2)}%` }}
                      transition={{ duration: 0.9, ease: "easeOut" }} />
                  </div>
                  <div className="mt-1.5 font-mono text-[11px] text-slate-400">{m.id}{na ? " · bought once" : ""}</div>
                </motion.div>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

export function Findings({ findings }: { findings: Finding[] }) {
  return (
    <div className="space-y-4">
      {groups(findings).map(([dim, fs]) => (
        <div key={dim} className="rounded-xl border border-slate-200 bg-white">
          <div className="border-b border-slate-100 px-4 py-2 text-[12px] font-semibold uppercase tracking-wider text-slate-400">{dim}</div>
          <ul className="divide-y divide-slate-100">
            {fs.map((f) => (
              <li key={f.ref} className="flex flex-wrap items-start gap-3 px-4 py-3">
                <span className="w-12 shrink-0 font-mono text-[12px] text-slate-400">{f.ref}</span>
                <div className="min-w-0 flex-1">
                  <div className="text-[13.5px] font-medium text-slate-800">{f.title}</div>
                  <div className="text-[12.5px] text-slate-500">{f.text}</div>
                </div>
                <Chip tone={RUBRIC_TONE[f.state] ?? "slate"}>{words(f.state)}</Chip>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

export function Evidence({ evidence }: { evidence: EvidenceView[] }) {
  if (!evidence.length) return <p className="text-sm text-slate-500">No evidence recorded yet.</p>;
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <ul className="divide-y divide-slate-100">
        {evidence.map((e, i) => (
          <motion.li key={e.id} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.03 * i }} className="flex flex-wrap gap-3 px-4 py-3">
            <span className="w-10 shrink-0 font-mono text-[12px] text-slate-400">{e.id}</span>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-[13px] font-medium text-slate-800">{words(e.type)}</span>
                <Chip tone={e.demand ? "emerald" : "slate"}>rung {e.rung.slice(1)} · {e.demand ? "counts as demand" : "not demand"}</Chip>
                {!e.independent && <Chip tone="amber">not independent</Chip>}
                {e.fromSegment && <Chip tone="sky">from the segment</Chip>}
              </div>
              <p className="mt-1 text-[12.5px] text-slate-600">{e.summary}</p>
              <p className="mt-0.5 text-[11.5px] text-slate-400">{e.source}{e.supports.length ? ` · supports ${e.supports.join(", ")}` : ""}{e.contradicts.length ? ` · against ${e.contradicts.join(", ")}` : ""}</p>
            </div>
          </motion.li>
        ))}
      </ul>
    </div>
  );
}
