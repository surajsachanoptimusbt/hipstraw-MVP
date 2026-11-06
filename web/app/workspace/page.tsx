"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { ArrowRight, CalendarClock, Megaphone, Plus, Radar } from "lucide-react";
import { MiniPipeline } from "@/components/pipeline";
import { Card, Chip, Skeleton, StatePill } from "@/components/ui";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import { usePoll } from "@/lib/use-poll";

const ICON = { shadow_launch: Radar, day_zero: CalendarClock, campaign: Megaphone } as const;
const HREF = { shadow_launch: "/workspace/new", day_zero: "/workspace/day-zero", campaign: "/workspace/campaigns" } as const;

export default function WorkspaceHome() {
  const offerings = usePoll(api.offerings, 60000).data;
  const { data: cases } = usePoll(api.cases, 2500);

  return (
    <div>
      <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="mb-8">
        <div className="text-[13px] font-semibold text-indigo-600">Welcome back</div>
        <h1 className="mt-1 text-[32px] font-bold tracking-tight text-slate-900">Launch with evidence, <span className="brand-text">not guesses</span>.</h1>
        <p className="mt-2 max-w-2xl text-[15px] text-slate-600">
          Tell Hipstraw about your product and market. Its agent works your request with a proven playbook, a reviewer approves the
          plan, and you see every step.
        </p>
      </motion.div>

      <div className="mb-10 grid gap-4 md:grid-cols-3">
        {(offerings ?? []).map((o, i) => {
          const Icon = ICON[o.id as keyof typeof ICON] ?? Radar;
          return (
            <motion.div key={o.id} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 * i }} whileHover={{ y: -4 }}>
              <Link href={HREF[o.id as keyof typeof HREF] ?? "/workspace"}>
                <Card className="group h-full p-5 transition-shadow hover:shadow-xl hover:shadow-indigo-500/10">
                  <div className="flex items-start justify-between">
                    <span className="brand-gradient grid h-11 w-11 place-items-center rounded-xl text-white shadow-lg shadow-indigo-500/30"><Icon size={20} /></span>
                    <Chip tone={o.status === "live" ? "emerald" : "slate"} pulse={o.status === "live" ? true : undefined}>{o.status === "live" ? "Live" : "Preview"}</Chip>
                  </div>
                  <div className="mt-4 text-[17px] font-semibold text-slate-900">{o.name}</div>
                  <p className="mt-1 text-[13px] leading-relaxed text-slate-600">{o.summary}</p>
                  <div className="mt-4 inline-flex items-center gap-1 text-[13px] font-semibold text-indigo-700">
                    {o.status === "live" ? "Start a request" : "See the preview"} <ArrowRight size={14} className="transition group-hover:translate-x-1" />
                  </div>
                </Card>
              </Link>
            </motion.div>
          );
        })}
        {!offerings && [0, 1, 2].map((i) => <Skeleton key={i} className="h-48" />)}
      </div>

      <div className="mb-3 flex items-end justify-between">
        <div>
          <h2 className="text-[18px] font-semibold text-slate-900">Your requests</h2>
          <p className="text-[13px] text-slate-500">Live: the progress moves as Hipstraw works.</p>
        </div>
        <Link href="/workspace/new" className="brand-gradient inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-[13px] font-semibold text-white shadow-lg shadow-indigo-500/25">
          <Plus size={15} /> New request
        </Link>
      </div>
      <div className="space-y-3">
        {(cases ?? []).map((c, i) => (
          <motion.div key={c.id} layout initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 * i }}>
            <Link href={`/workspace/requests/${c.id}`}>
              <Card className="group flex flex-wrap items-center gap-5 p-4 transition hover:border-indigo-200">
                <div className="min-w-[220px] flex-1">
                  <div className="flex items-center gap-2"><span className="font-mono text-[12px] text-slate-400">{c.id}</span><span className="text-[15px] font-semibold text-slate-900">{c.company}</span></div>
                  <div className="truncate text-[13px] text-slate-500">{c.caseType} · {c.market}</div>
                </div>
                <MiniPipeline index={c.stageIndex} state={c.state} />
                <StatePill state={c.state} customer />
                <span className="w-16 text-right text-[12.5px] text-slate-400">{ago(c.createdAt)}</span>
                <ArrowRight size={16} className="text-slate-300 transition group-hover:translate-x-1 group-hover:text-indigo-600" />
              </Card>
            </Link>
          </motion.div>
        ))}
        {!cases && <Skeleton className="h-20" />}
      </div>
    </div>
  );
}
