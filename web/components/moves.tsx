"use client";

import { motion } from "motion/react";
import { Check, CircleDot, Lock } from "lucide-react";
import { EFFECT } from "@/lib/format";
import type { HypothesisPlay, MoveView } from "@/lib/types";
import { Chip, cx } from "./ui";

function MoveRow({ m, i, gated }: { m: MoveView; i: number; gated: boolean }) {
  const e = EFFECT[m.effect];
  return (
    <motion.li initial={{ opacity: 0, x: -10 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.035 * i }} className="relative flex gap-3 pb-4 last:pb-0">
      <div className="relative z-10 mt-0.5">
        {m.status === "done" ? (
          <span className="grid h-7 w-7 place-items-center rounded-full bg-emerald-500 text-white"><Check size={14} strokeWidth={3} /></span>
        ) : m.status === "next" ? (
          <span className="relative grid h-7 w-7 place-items-center rounded-full bg-indigo-600 text-white">
            <motion.span className="absolute inset-0 rounded-full bg-indigo-500" animate={{ scale: [1, 1.6], opacity: [0.5, 0] }} transition={{ duration: 1.5, repeat: Infinity }} />
            <CircleDot size={14} className="relative" />
          </span>
        ) : (
          <span className="grid h-7 w-7 place-items-center rounded-full border-2 border-slate-200 bg-white text-[11px] font-semibold text-slate-400">{m.stage}</span>
        )}
      </div>
      <div className={cx("min-w-0 flex-1 rounded-xl border p-3", m.status === "next" ? "border-indigo-200 bg-indigo-50/40" : "border-slate-200 bg-white")}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[12px] text-slate-500">{m.id}</span>
          <span className="text-[13.5px] font-semibold text-slate-900">{m.name}</span>
          <Chip tone={e.tone}>{m.effect} · {e.label}</Chip>
          {m.needsCharter && (
            <Chip tone={gated ? "amber" : "emerald"}><Lock size={11} /> {gated ? "Needs approval" : "Chartered"}</Chip>
          )}
          {m.status !== "planned" && <Chip tone={m.status === "done" ? "emerald" : "brand"}>{m.status}</Chip>}
        </div>
        <p className="mt-1 text-[12.5px] leading-relaxed text-slate-600">{m.does}</p>
        {(m.records.length > 0 || m.passWhen.length > 0) && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {m.records.map((r) => <span key={r} className="rounded-md bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">records {r}</span>)}
            {m.passWhen.map((p) => <span key={p} className="rounded-md bg-violet-50 px-1.5 py-0.5 text-[11px] text-violet-700">pass when {p}</span>)}
          </div>
        )}
      </div>
    </motion.li>
  );
}

/** The workflow of one hypothesis: each task's Line, its Moves in order, gated until a reviewer approves. */
export function Moves({ h, approved }: { h: HypothesisPlay; approved: boolean }) {
  let n = 0;
  return (
    <div className="space-y-5">
      {h.tasks.map((t) => (
        <div key={t.taskId}>
          <div className="mb-2 flex items-center gap-2 text-[13px]">
            <span className="font-semibold text-slate-900">{t.taskId} {t.task}</span>
            <span className="text-slate-400">·</span>
            <span className={t.lineId ? "font-medium text-indigo-700" : "text-slate-400"}>{t.lineId ? `${t.lineId} ${t.lineName}` : "No Line"}</span>
          </div>
          {t.moves.length ? (
            <ol className="relative pl-0">
              <span className="absolute bottom-3 left-[13px] top-3 w-px bg-slate-200" />
              {t.moves.map((m) => <MoveRow key={`${t.taskId}-${m.id}-${m.stage}`} m={m} i={n++} gated={!approved} />)}
            </ol>
          ) : (
            <p className="rounded-xl border border-dashed border-slate-200 px-3 py-2 text-[12.5px] text-slate-500">{t.reason}</p>
          )}
        </div>
      ))}
    </div>
  );
}
