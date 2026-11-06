"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { ChevronRight, Layers, ListChecks, Route, ScanSearch, Gauge, FileText } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { ActivityFeed } from "@/components/activity-feed";
import { AgentOrb } from "@/components/agent-orb";
import { ApprovalPanel } from "@/components/approval";
import { Evidence, Findings, Metrics } from "@/components/insights";
import { HypothesisLines, LineMatrix } from "@/components/lines";
import { Moves } from "@/components/moves";
import { PipelineStepper, STAGE_ORDER } from "@/components/pipeline";
import { Card, Chip, SectionTitle, Skeleton, StatePill, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { ago, plural, words } from "@/lib/format";
import type { CaseDetail, LedgerEvent, StageView } from "@/lib/types";
import { usePoll } from "@/lib/use-poll";

const TABS = [
  { key: "lines", label: "Lines", icon: Route },
  { key: "moves", label: "Moves", icon: ListChecks },
  { key: "metrics", label: "Metrics", icon: Gauge },
  { key: "findings", label: "Findings", icon: ScanSearch },
  { key: "evidence", label: "Evidence", icon: FileText },
] as const;

/** The stages as they stood after the given events: used to replay a run. */
function stagesAt(stages: StageView[], events: LedgerEvent[]): StageView[] {
  const last = events.length ? STAGE_ORDER.indexOf(events[events.length - 1].stage) : 0;
  return stages.map((s, i) => ({ ...s, status: i < last ? "done" : i === last ? "active" : "pending" }));
}

export default function CasePage() {
  const { id } = useParams<{ id: string }>();
  const [ms, setMs] = useState(1000);
  const { data, error, setData } = usePoll(() => api.case(id), ms, id);
  const [replay, setReplay] = useState<{ on: boolean; n: number }>({ on: false, n: 0 });
  const [hyp, setHyp] = useState<string | null>(null);
  const [tab, setTab] = useState<(typeof TABS)[number]["key"]>("lines");
  const working = data?.case.state === "agent_working";

  useEffect(() => setMs(working ? 700 : 4000), [working]);
  useEffect(() => {
    if (!replay.on || !data) return;
    if (replay.n >= data.events.length) {
      const t = setTimeout(() => setReplay({ on: false, n: 0 }), 600);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setReplay((r) => ({ ...r, n: r.n + 1 })), 360);
    return () => clearTimeout(t);
  }, [replay, data]);

  const events = useMemo(() => (data ? (replay.on ? data.events.slice(0, replay.n) : data.events) : []), [data, replay]);
  const stages = useMemo(() => (data ? (replay.on ? stagesAt(data.stages, events) : data.stages) : []), [data, replay.on, events]);

  if (error && !data) return <p className="text-sm text-rose-600">Cannot load {id}: {error}</p>;
  if (!data) return <div className="space-y-4"><Skeleton className="h-28" /><Skeleton className="h-36" /><Skeleton className="h-96" /></div>;

  const c = data.case;
  const rec = data.recommendation;
  const h = rec?.hypotheses.find((x) => x.id === hyp) ?? rec?.hypotheses[0];
  const stageName = data.stages.find((s) => s.key === c.stage)?.name ?? words(c.stage);
  const status = {
    agent_working: `Agent working · ${stageName}`,
    waiting_review: "Waiting on you: approve the plan",
    approved: "Approved · executors run the Moves",
    returned: "Returned to the customer",
  }[c.state];

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-1.5 text-[13px] text-slate-500">
        <Link href="/desk" className="hover:text-slate-900">Review queue</Link><ChevronRight size={14} /><span className="font-mono text-slate-700">{c.id}</span>
      </div>

      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
        <Card className="flex flex-wrap items-center justify-between gap-6 p-6">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-slate-900 px-2 py-0.5 font-mono text-[12px] font-semibold text-white">{c.id}</span>
              <Chip tone="sky">{c.caseType}</Chip><Chip tone="brand">Shadow launch</Chip><StatePill state={c.state} />
            </div>
            <h1 className="mt-2 text-[26px] font-bold tracking-tight text-slate-900">{c.company}</h1>
            <p className="text-[14px] text-slate-600">{c.market}{data.thesis.geography ? ` · ${data.thesis.geography}` : ""}</p>
            <p className="mt-1 text-[12.5px] text-slate-400">Requested by {c.requestedBy} · {ago(c.createdAt)} ago · {plural(c.hypotheses, "hypothesis", "hypotheses")}</p>
          </div>
          <div className="flex items-center gap-4 rounded-2xl bg-slate-50 px-5 py-3">
            <AgentOrb working={working || replay.on} />
            <div>
              <div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Hipstraw agent</div>
              <AnimatePresence mode="wait">
                <motion.div key={replay.on ? "replay" : status} initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }}
                  className="text-[14px] font-semibold text-slate-800">{replay.on ? "Replaying the run…" : status}</motion.div>
              </AnimatePresence>
              <div className="text-[12px] text-slate-500">Rules only: the rubric judges, the playbook picks</div>
            </div>
          </div>
        </Card>
      </motion.div>

      <Card className="px-4 py-6"><PipelineStepper stages={stages} working={working || replay.on} /></Card>

      <div className="grid gap-5 lg:grid-cols-12">
        <Card className="overflow-hidden lg:col-span-5">
          <ActivityFeed events={events} working={working} replaying={replay.on}
            onReplay={() => setReplay({ on: true, n: 0 })} />
        </Card>
        <div className="space-y-5 lg:col-span-7">
          <ApprovalPanel detail={data} onDone={(d: CaseDetail) => setData(d)} />
          <Card className="p-5">
            <SectionTitle title="Lines decided for each task" hint="Picked by the playbook's rules. Select a hypothesis to see the Lines that were available."
              right={<Chip tone="slate"><Layers size={12} /> {rec?.repertoireVersion ?? "playbook"}</Chip>} />
            {rec ? <LineMatrix rec={rec} selected={h?.id} onSelect={setHyp} /> : (
              <div className="space-y-2"><Skeleton className="h-10" /><Skeleton className="h-10" /><Skeleton className="h-10" />
                <p className="pt-1 text-[12.5px] text-slate-500">The picks appear when the agent reaches Recommend.</p></div>
            )}
          </Card>
        </div>
      </div>

      {rec && h && (
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}>
          <Card className="p-5">
            <div className="mb-4 flex flex-wrap items-center gap-2">
              {rec.hypotheses.map((x) => (
                <button key={x.id} onClick={() => setHyp(x.id)}
                  className={cx("relative rounded-xl px-3.5 py-2 text-left transition", x.id === h.id ? "text-white" : "text-slate-600 hover:bg-slate-100")}>
                  {x.id === h.id && <motion.span layoutId="hyp-pill" className="brand-gradient absolute inset-0 rounded-xl shadow-md shadow-indigo-500/25" />}
                  <span className="relative text-[13px] font-semibold">{x.id} {x.name}</span>
                </button>
              ))}
            </div>
            <div className="mb-4 grid gap-3 rounded-xl bg-slate-50 p-4 text-[13px] md:grid-cols-3">
              <div><div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Segment</div><div className="text-slate-800">{h.segment}</div></div>
              <div><div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Offering</div><div className="text-slate-800">{h.offering}</div></div>
              <div><div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Position</div>
                <div className="text-slate-800">{words(h.decision)} · <span className="text-slate-500">{h.checkpoint}</span></div></div>
              <div className="md:col-span-3"><div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">First action</div>
                <div className="text-slate-800">{h.firstAction}</div></div>
            </div>
            <div className="mb-4 flex gap-1 border-b border-slate-200">
              {TABS.map((t) => (
                <button key={t.key} onClick={() => setTab(t.key)} className={cx("relative flex items-center gap-1.5 px-3.5 py-2.5 text-[13.5px] font-medium",
                  tab === t.key ? "text-indigo-700" : "text-slate-500 hover:text-slate-800")}>
                  <t.icon size={15} /> {t.label}
                  {tab === t.key && <motion.span layoutId="case-tab" className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-indigo-600" />}
                </button>
              ))}
            </div>
            <AnimatePresence mode="wait">
              <motion.div key={`${h.id}-${tab}`} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.18 }}>
                {tab === "lines" && <HypothesisLines h={h} />}
                {tab === "moves" && <Moves h={h} approved={c.state === "approved"} />}
                {tab === "metrics" && <Metrics metrics={h.metrics} />}
                {tab === "findings" && <Findings findings={h.findings} />}
                {tab === "evidence" && <Evidence evidence={h.evidence} />}
              </motion.div>
            </AnimatePresence>
          </Card>
        </motion.div>
      )}
    </div>
  );
}
