"use client";

import { motion } from "motion/react";
import { Check, FileInput, Route, ScanSearch, Target, UserCheck, Workflow } from "lucide-react";
import { cx } from "./ui";
import type { StageKey, StageView } from "@/lib/types";

export const STAGE_ICON: Record<StageKey, typeof Check> = {
  ingest: FileInput, review: ScanSearch, position: Target, recommend: Route, workflow: Workflow, approval: UserCheck,
};

export const STAGE_ORDER: StageKey[] = ["ingest", "review", "position", "recommend", "workflow", "approval"];

/** The six stages of a request. The line between them fills as the agent moves; the active stage pulses. */
export function PipelineStepper({ stages, working }: { stages: StageView[]; working: boolean }) {
  const active = Math.max(0, stages.findIndex((s) => s.status === "active"));
  const allDone = stages.every((s) => s.status === "done");
  const fill = allDone ? 1 : active / (stages.length - 1);
  return (
    <div className="relative px-2">
      <div className="absolute left-[calc(100%/12)] right-[calc(100%/12)] top-6 h-1 rounded-full bg-slate-200" />
      <motion.div className="flowing absolute left-[calc(100%/12)] top-6 h-1 rounded-full"
        initial={false} animate={{ width: `calc((100% - 100%/6) * ${fill})` }} transition={{ duration: 0.7, ease: "easeInOut" }} />
      <div className="relative grid grid-cols-6 gap-2">
        {stages.map((s, i) => {
          const Icon = STAGE_ICON[s.key];
          const done = s.status === "done";
          const on = s.status === "active";
          return (
            <div key={s.key} className="flex flex-col items-center text-center">
              <div className="relative">
                {on && (
                  <motion.span className="absolute inset-0 rounded-2xl bg-indigo-400/40"
                    animate={{ scale: [1, 1.45], opacity: [0.6, 0] }} transition={{ duration: 1.4, repeat: Infinity }} />
                )}
                <motion.div layout
                  className={cx("relative grid h-12 w-12 place-items-center rounded-2xl border-2 transition-colors",
                    done && "border-emerald-500 bg-emerald-500 text-white shadow-md shadow-emerald-500/30",
                    on && "brand-gradient border-transparent text-white shadow-lg shadow-indigo-500/40",
                    !done && !on && "border-slate-200 bg-white text-slate-400")}
                  initial={false} animate={{ scale: on ? 1.08 : 1 }} transition={{ type: "spring", stiffness: 260, damping: 18 }}>
                  {done ? (
                    <motion.span initial={{ scale: 0, rotate: -40 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: "spring", stiffness: 300, damping: 14, delay: 0.05 * i }}>
                      <Check size={22} strokeWidth={3} />
                    </motion.span>
                  ) : (
                    <Icon size={21} />
                  )}
                </motion.div>
              </div>
              <div className={cx("mt-2 text-[13px] font-semibold", on ? "text-indigo-700" : done ? "text-slate-800" : "text-slate-400")}>{s.name}</div>
              <div className="hidden text-[11.5px] leading-tight text-slate-500 md:block">{s.what}</div>
              {on && working && <div className="mt-1 text-[11px] font-medium text-indigo-600">working…</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/** Six small dots for a table row: done, active, pending. */
export function MiniPipeline({ index, state }: { index: number; state: string }) {
  const finished = state === "approved" || state === "returned";
  return (
    <div className="flex items-center gap-1">
      {STAGE_ORDER.map((k, i) => {
        const done = i < index || finished;
        const on = i === index && !finished;
        return (
          <span key={k} className={cx("h-1.5 rounded-full transition-all",
            done ? "w-4 bg-emerald-500" : on ? "w-6 flowing" : "w-4 bg-slate-200")} />
        );
      })}
    </div>
  );
}
