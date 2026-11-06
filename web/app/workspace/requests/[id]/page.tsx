"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { BadgeCheck, ChevronRight, Hourglass, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";
import { ActivityFeed } from "@/components/activity-feed";
import { AgentOrb } from "@/components/agent-orb";
import { LineMatrix } from "@/components/lines";
import { PipelineStepper } from "@/components/pipeline";
import { Card, SectionTitle, Skeleton, StatePill } from "@/components/ui";
import { api } from "@/lib/api";
import { STATE, clock } from "@/lib/format";
import { usePoll } from "@/lib/use-poll";

export default function RequestPage() {
  const { id } = useParams<{ id: string }>();
  const [ms, setMs] = useState(800);
  const { data } = usePoll(() => api.case(id), ms, id);
  const working = data?.case.state === "agent_working";
  useEffect(() => setMs(working ? 700 : 4000), [working]);
  if (!data) return <div className="space-y-4"><Skeleton className="h-32" /><Skeleton className="h-40" /><Skeleton className="h-80" /></div>;

  const c = data.case;
  const rec = data.recommendation;
  const say = {
    agent_working: "Hipstraw's agent is working on your request",
    waiting_review: "Your plan is with a Hipstraw reviewer",
    approved: "Your plan is approved: the first Moves can start",
    returned: "Your plan came back with a note",
  }[c.state];

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-1.5 text-[13px] text-slate-500">
        <Link href="/workspace" className="hover:text-slate-900">Your requests</Link><ChevronRight size={14} /><span className="text-slate-700">{c.company}</span>
      </div>
      <Card className="relative overflow-hidden p-7">
        <div className="brand-gradient absolute -right-24 -top-24 h-64 w-64 rounded-full opacity-10 blur-2xl" />
        <div className="relative flex flex-wrap items-center gap-6">
          <AgentOrb working={working} size={72} />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2"><span className="font-mono text-[12px] text-slate-400">{c.id}</span><StatePill state={c.state} customer /></div>
            <AnimatePresence mode="wait">
              <motion.h1 key={c.state} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }}
                className="mt-1 text-[24px] font-bold tracking-tight text-slate-900">{say}</motion.h1>
            </AnimatePresence>
            <p className="text-[14px] text-slate-600">{c.company} · {c.market}</p>
          </div>
        </div>
      </Card>

      <Card className="px-4 py-6"><PipelineStepper stages={data.stages} working={working} /></Card>

      <div className="grid gap-5 lg:grid-cols-12">
        <Card className="overflow-hidden lg:col-span-5"><ActivityFeed events={data.events} working={working} compact /></Card>
        <div className="space-y-5 lg:col-span-7">
          <Card className="p-5">
            {data.approval ? (
              <div className="flex items-start gap-3">
                <span className={`grid h-10 w-10 place-items-center rounded-full text-white ${data.approval.action === "approve" ? "bg-emerald-500" : "bg-rose-500"}`}>
                  {data.approval.action === "approve" ? <BadgeCheck size={20} /> : <Undo2 size={20} />}
                </span>
                <div>
                  <div className="text-[15px] font-semibold text-slate-900">{STATE[c.state].customer}</div>
                  <div className="text-[12.5px] text-slate-500">{data.approval.actor} · {clock(data.approval.at)}</div>
                  {data.approval.note && <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-[13px] text-slate-700">“{data.approval.note}”</p>}
                </div>
              </div>
            ) : (
              <div className="flex items-center gap-3 text-[14px] text-slate-600">
                <Hourglass size={18} className="text-amber-500" />
                {working ? "When the agent has laid out the plan, a reviewer approves it before anything contacts people or spends." : "A Hipstraw reviewer is checking the plan."}
              </div>
            )}
          </Card>
          <Card className="p-5">
            <SectionTitle title="Your plan" hint="For each task, the Line the playbook picked for each of your hypotheses" />
            {rec ? <LineMatrix rec={rec} /> : <div className="space-y-2"><Skeleton className="h-10" /><Skeleton className="h-10" /></div>}
          </Card>
          {rec && (
            <Card className="p-5">
              <SectionTitle title="What happens first" />
              <ul className="space-y-2.5">
                {rec.hypotheses.map((h) => (
                  <li key={h.id} className="rounded-xl bg-slate-50 px-4 py-3 text-[13px]">
                    <div className="font-semibold text-slate-900">{h.id} {h.name}</div>
                    <div className="text-slate-600">{h.firstAction}</div>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
