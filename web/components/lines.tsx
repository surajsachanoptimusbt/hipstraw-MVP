"use client";

import { motion } from "motion/react";
import { Check, Lock, Route, X } from "lucide-react";
import type { HypothesisPlay, Recommendation, TaskPlay } from "@/lib/types";
import { Chip, cx } from "./ui";

/** Tasks against hypotheses: the Line the playbook picked in each cell. */
export function LineMatrix({ rec, selected, onSelect }: {
  rec: Recommendation; selected?: string; onSelect?: (hypothesis: string) => void;
}) {
  const tasks = rec.hypotheses[0]?.tasks ?? [];
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-separate border-spacing-0 text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 bg-white px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400">Task</th>
            {rec.hypotheses.map((h) => (
              <th key={h.id} className="px-3 py-2 text-left">
                <button onClick={() => onSelect?.(h.id)}
                  className={cx("rounded-lg px-2 py-1 text-left text-[12px] font-semibold transition",
                    selected === h.id ? "bg-indigo-50 text-indigo-700" : "text-slate-600 hover:bg-slate-50")}>
                  {h.id} <span className="font-medium">{h.name}</span>
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {tasks.map((t, row) => (
            <tr key={t.taskId}>
              <td className="sticky left-0 border-t border-slate-100 bg-white px-3 py-3 align-top">
                <div className="text-[13px] font-semibold text-slate-800">{t.taskId} {t.task}</div>
                <div className="text-[11.5px] text-slate-500">from {t.options.map((o) => o.lineId).join(", ")}</div>
              </td>
              {rec.hypotheses.map((h, col) => {
                const cell = h.tasks[row];
                return (
                  <td key={h.id} className="border-t border-slate-100 px-3 py-3 align-top">
                    <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.03 * (row * 4 + col) }}>
                      {cell.lineId ? (
                        <span className="inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-indigo-50 to-violet-50 px-2.5 py-1 text-[12.5px] font-semibold text-indigo-800 ring-1 ring-indigo-200">
                          <Route size={13} /> {cell.lineId} {cell.lineName}
                        </span>
                      ) : (
                        <span className="inline-flex rounded-lg bg-slate-50 px-2.5 py-1 text-[12.5px] text-slate-400 ring-1 ring-slate-200">No Line</span>
                      )}
                      <div className="mt-1 text-[11px] text-slate-500">
                        {cell.options.filter((o) => o.eligible).length} of {cell.options.length} eligible
                      </div>
                    </motion.div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** One task: every Line available, its conditions checked, the eligible ones ranked, the first picked. */
export function TaskOptions({ task, index }: { task: TaskPlay; index: number }) {
  return (
    <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 * index }}
      className="rounded-2xl border border-slate-200 bg-slate-50/60 p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <div className="text-[14px] font-semibold text-slate-900">{task.taskId} · {task.task}</div>
          <div className="text-[12.5px] text-slate-500">{task.question}</div>
        </div>
        <Chip tone={task.lineId ? "brand" : "slate"}>{task.lineId ? `Picked ${task.lineId}` : "No Line eligible"}</Chip>
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        {task.options.map((o) => (
          <motion.div key={o.lineId} layout
            className={cx("relative rounded-xl bg-white p-3.5",
              o.picked ? "ring-gradient shadow-lg shadow-indigo-500/10" : "border border-slate-200",
              !o.eligible && "opacity-70")}>
            {o.picked && (
              <motion.span initial={{ scale: 0 }} animate={{ scale: 1 }} transition={{ type: "spring", stiffness: 300, damping: 15, delay: 0.15 }}
                className="brand-gradient absolute -right-2 -top-2 grid h-6 w-6 place-items-center rounded-full text-white shadow-md">
                <Check size={14} strokeWidth={3} />
              </motion.span>
            )}
            <div className="flex items-start justify-between gap-2">
              <div>
                <div className="text-[13.5px] font-semibold text-slate-900"><span className="font-mono text-[12px] text-slate-500">{o.lineId}</span> {o.name}</div>
                <div className="mt-0.5 text-[12px] leading-snug text-slate-500">{o.purpose}</div>
              </div>
            </div>
            <div className="mt-2.5 flex flex-wrap gap-1.5">
              {o.checks.map((c) => (
                <span key={c.text} className={cx("inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11.5px] font-medium",
                  c.ok ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700")}>
                  {c.ok ? <Check size={11} strokeWidth={3} /> : <X size={11} strokeWidth={3} />} {c.text}
                </span>
              ))}
            </div>
            <div className="mt-2.5 flex items-center justify-between text-[11.5px]">
              <span className="font-mono text-slate-400">{o.moves.join(" → ")}</span>
              <span className={cx("font-semibold", o.picked ? "text-indigo-700" : o.eligible ? "text-slate-500" : "text-slate-400")}>
                {o.picked ? `Picked · rank ${o.rank}` : o.eligible ? `Eligible · rank ${o.rank}` : "Not eligible"}
              </span>
            </div>
          </motion.div>
        ))}
      </div>
      <p className="mt-3 text-[12px] text-slate-500">{task.reason}</p>
    </motion.div>
  );
}

export function HypothesisLines({ h }: { h: HypothesisPlay }) {
  return (
    <div className="space-y-3">
      {h.tasks.map((t, i) => <TaskOptions key={t.taskId} task={t} index={i} />)}
      <p className="flex items-center gap-1.5 text-[12px] text-slate-500">
        <Lock size={12} /> Lines and Moves are predefined; the playbook&apos;s rules pick them. No model decides.
      </p>
    </div>
  );
}
