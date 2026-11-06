"use client";

import { motion } from "motion/react";
import { Check, CircleDot, Eye, Flag, Rocket } from "lucide-react";
import { Card, Chip, cx } from "@/components/ui";

// A sample plan that shows the offering. Not live data: Day Zero launch is not yet wired to the desk.
const TODAY = -12;
const PHASES = [
  { name: "Prepare", span: "T-30 to T-15", from: -30, to: -15, items: [
    { t: -30, what: "Mandate and Day Zero date agreed", done: true },
    { t: -27, what: "Readiness criteria set for every channel", done: true },
    { t: -22, what: "Campaign assets captured as evidence", done: true },
    { t: -18, what: "Tracking and metric sources verified", done: true },
  ] },
  { name: "Readiness", span: "T-14 to T-1", from: -14, to: -1, items: [
    { t: -14, what: "Day Zero dependency check", done: true },
    { t: -12, what: "Completeness check against the criteria", done: false },
    { t: -7, what: "Blockers escalated to the sponsor", done: false },
    { t: -2, what: "Final review and go / no-go", done: false },
  ] },
  { name: "Launch day", span: "T0", from: 0, to: 0, items: [
    { t: 0, what: "Launch, with the live checkpoint armed", done: false },
  ] },
  { name: "After launch", span: "T+1 to T+30", from: 1, to: 30, items: [
    { t: 1, what: "Metric identity and freshness verified", done: false },
    { t: 7, what: "First live checkpoint: observations and deltas", done: false },
    { t: 14, what: "Strategy assumptions reviewed against results", done: false },
    { t: 30, what: "Launch review and report", done: false },
  ] },
];

const pos = (t: number) => ((t + 30) / 60) * 100;

export default function DayZero() {
  return (
    <div>
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[13px] font-semibold text-indigo-600">Day Zero launch</div>
          <h1 className="mt-1 text-[28px] font-bold tracking-tight text-slate-900">Every day from T-30 to launch, and after</h1>
          <p className="mt-1 max-w-2xl text-[14px] text-slate-600">Hipstraw lays out what has to be done before your release day, tracks what has been done, and keeps going after launch.</p>
        </div>
        <Chip tone="amber"><Eye size={12} /> Preview: a sample plan, not live data</Chip>
      </motion.div>

      <Card className="mb-6 overflow-x-auto p-6">
        <div className="relative h-28 min-w-[760px]">
          <div className="absolute left-0 right-0 top-10 h-1.5 rounded-full bg-slate-100" />
          <motion.div className="flowing absolute left-0 top-10 h-1.5 rounded-full" initial={{ width: 0 }} animate={{ width: `${pos(TODAY)}%` }} transition={{ duration: 1.4, ease: "easeInOut" }} />
          {[-30, -21, -14, -7, 0, 7, 14, 21, 30].map((t) => (
            <div key={t} className="absolute top-[76px] -translate-x-1/2 text-[11.5px] font-medium text-slate-400" style={{ left: `${pos(t)}%` }}>{t === 0 ? "T0" : t < 0 ? `T${t}` : `T+${t}`}</div>
          ))}
          <motion.div className="absolute top-3 -translate-x-1/2" initial={{ left: "0%" }} animate={{ left: `${pos(TODAY)}%` }} transition={{ duration: 1.4, ease: "easeInOut" }}>
            <div className="rounded-full bg-ink px-2.5 py-0.5 text-[11px] font-semibold text-white">Today · T{TODAY}</div>
          </motion.div>
          <div className="absolute top-6 -translate-x-1/2" style={{ left: `${pos(0)}%` }}>
            <motion.div animate={{ scale: [1, 1.15, 1] }} transition={{ duration: 1.6, repeat: Infinity }}
              className="brand-gradient grid h-10 w-10 place-items-center rounded-full text-white shadow-lg shadow-indigo-500/40"><Rocket size={18} /></motion.div>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {PHASES.map((p, i) => {
          const current = TODAY >= p.from && TODAY <= p.to;
          return (
            <motion.div key={p.name} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 * i }}>
              <Card className={cx("h-full p-5", current && "ring-gradient")}>
                <div className="flex items-center justify-between">
                  <div className="text-[16px] font-semibold text-slate-900">{p.name}</div>
                  {current ? <Chip tone="brand" pulse>Now</Chip> : p.to < TODAY ? <Chip tone="emerald">Done</Chip> : <Chip tone="slate">Ahead</Chip>}
                </div>
                <div className="text-[12.5px] text-slate-500">{p.span}</div>
                <ul className="mt-4 space-y-3">
                  {p.items.map((it) => (
                    <li key={it.what} className="flex gap-2.5">
                      {it.done ? <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-emerald-500 text-white"><Check size={12} strokeWidth={3} /></span>
                        : it.t === TODAY ? <CircleDot size={20} className="shrink-0 text-indigo-600" />
                        : it.t === 0 ? <Flag size={18} className="shrink-0 text-slate-400" />
                        : <span className="mt-1 h-3.5 w-3.5 shrink-0 rounded-full border-2 border-slate-300" />}
                      <div>
                        <div className={cx("text-[13px]", it.done ? "text-slate-500 line-through decoration-slate-300" : "text-slate-800")}>{it.what}</div>
                        <div className="text-[11px] text-slate-400">{it.t === 0 ? "T0" : it.t < 0 ? `T${it.t}` : `T+${it.t}`}</div>
                      </div>
                    </li>
                  ))}
                </ul>
              </Card>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
