"use client";

import Link from "next/link";
import { AnimatePresence, motion } from "motion/react";
import { ArrowRight, Bot, CheckCheck, Inbox, UserCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { MiniPipeline } from "@/components/pipeline";
import { Card, Chip, CountUp, Skeleton, StatePill, WaitingLabel, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import type { CaseSummary } from "@/lib/types";
import { usePoll } from "@/lib/use-poll";

const FILTERS: { key: string; label: string; test: (c: CaseSummary) => boolean }[] = [
  { key: "open", label: "All open", test: (c) => c.state !== "approved" && c.state !== "returned" },
  { key: "mine", label: "Waiting on me", test: (c) => c.waitingOn === "reviewer" },
  { key: "agent", label: "Agent working", test: (c) => c.state === "agent_working" },
  { key: "done", label: "Decided", test: (c) => c.state === "approved" || c.state === "returned" },
  { key: "all", label: "Everything", test: () => true },
];

export default function Queue() {
  const { data, error } = usePoll(api.cases, 2000);
  const [filter, setFilter] = useState("open");
  const cases = useMemo(() => data ?? [], [data]);
  const shown = cases.filter(FILTERS.find((f) => f.key === filter)!.test);
  const stats = [
    { label: "Open requests", value: cases.filter(FILTERS[0].test).length, icon: Inbox, tone: "from-slate-700 to-slate-900" },
    { label: "Waiting on me", value: cases.filter((c) => c.waitingOn === "reviewer").length, icon: UserCheck, tone: "from-amber-400 to-orange-500" },
    { label: "Agent working", value: cases.filter((c) => c.state === "agent_working").length, icon: Bot, tone: "from-indigo-500 to-violet-600" },
    { label: "Approved", value: cases.filter((c) => c.state === "approved").length, icon: CheckCheck, tone: "from-emerald-400 to-teal-500" },
  ];

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-bold tracking-tight text-slate-900">Review queue</h1>
          <p className="mt-1 text-[14px] text-slate-500">Every request, what the agent is doing with it, and what waits on a person.</p>
        </div>
        <Chip tone="brand" pulse>Live · updates every 2 s</Chip>
      </motion.div>

      <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        {stats.map((s, i) => (
          <motion.div key={s.label} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 * i }}>
            <Card className="flex items-center gap-4 p-4">
              <div className={cx("grid h-11 w-11 place-items-center rounded-xl bg-gradient-to-br text-white shadow-md", s.tone)}><s.icon size={20} /></div>
              <div>
                <CountUp value={s.value} className="text-[26px] font-bold leading-none tabular-nums text-slate-900" />
                <div className="mt-1 text-[12.5px] text-slate-500">{s.label}</div>
              </div>
            </Card>
          </motion.div>
        ))}
      </div>

      <Card className="overflow-hidden">
        <div className="flex flex-wrap items-center gap-1 border-b border-slate-100 px-4 py-3">
          {FILTERS.map((f) => (
            <button key={f.key} onClick={() => setFilter(f.key)} className="relative rounded-full px-3.5 py-1.5 text-[13px] font-medium">
              {filter === f.key && <motion.span layoutId="queue-filter" className="absolute inset-0 rounded-full bg-ink" transition={{ type: "spring", stiffness: 400, damping: 32 }} />}
              <span className={cx("relative", filter === f.key ? "text-white" : "text-slate-500 hover:text-slate-800")}>
                {f.label} <span className="opacity-60">({cases.filter(f.test).length})</span>
              </span>
            </button>
          ))}
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[920px] text-left text-sm">
            <thead>
              <tr className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                {["Case", "Company", "Case type", "State", "Waiting on", "Pipeline", "Age", ""].map((h) => <th key={h} className="px-5 py-3">{h}</th>)}
              </tr>
            </thead>
            <tbody>
              {!data && !error && [0, 1, 2].map((i) => (
                <tr key={i}><td colSpan={8} className="px-5 py-3"><Skeleton className="h-9 w-full" /></td></tr>
              ))}
              <AnimatePresence initial={true}>
                {shown.map((c, i) => (
                  <motion.tr key={c.id} layout initial={{ opacity: 0, y: 10, backgroundColor: "rgba(99,102,241,0.10)" }}
                    animate={{ opacity: 1, y: 0, backgroundColor: "rgba(255,255,255,0)" }} exit={{ opacity: 0 }}
                    transition={{ delay: 0.04 * i, duration: 0.5 }} className="group border-t border-slate-100 hover:bg-slate-50/80">
                    <td className="px-5 py-4 font-mono text-[12.5px] font-semibold text-slate-700">{c.id}</td>
                    <td className="px-5 py-4">
                      <div className="font-semibold text-slate-900">{c.company}</div>
                      <div className="max-w-[260px] truncate text-[12.5px] text-slate-500">{c.market}</div>
                    </td>
                    <td className="px-5 py-4"><Chip tone="sky">{c.caseType}</Chip></td>
                    <td className="px-5 py-4"><StatePill state={c.state} /></td>
                    <td className="px-5 py-4"><WaitingLabel waiting={c.waitingOn} /></td>
                    <td className="px-5 py-4"><MiniPipeline index={c.stageIndex} state={c.state} /></td>
                    <td className="px-5 py-4 text-slate-500">{ago(c.createdAt)}</td>
                    <td className="px-5 py-4 text-right">
                      <Link href={`/desk/cases/${c.id}`} className="inline-flex items-center gap-1 rounded-lg border border-slate-200 px-3 py-1.5 text-[12.5px] font-semibold text-slate-700 transition group-hover:border-indigo-300 group-hover:text-indigo-700">
                        Open <ArrowRight size={13} />
                      </Link>
                    </td>
                  </motion.tr>
                ))}
              </AnimatePresence>
            </tbody>
          </table>
          {data && !shown.length && <div className="px-5 py-12 text-center text-sm text-slate-500">Nothing here. Requests from the customer workspace appear at once.</div>}
          {error && <div className="px-5 py-10 text-center text-sm text-rose-600">Cannot reach the desk API: {error}. Start it with <code className="font-mono">hipstraw-mm desk serve</code>.</div>}
        </div>
        <div className="border-t border-slate-100 px-5 py-3 text-[12px] text-slate-500">
          Each case type has its own Lines. The playbook picks the Line for every task; you see the Lines that were available and why one was picked.
        </div>
      </Card>
    </div>
  );
}
