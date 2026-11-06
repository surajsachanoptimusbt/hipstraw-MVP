"use client";

import { AnimatePresence, motion } from "motion/react";
import { ChevronDown, Lock, Route } from "lucide-react";
import { useState } from "react";
import { Card, Chip, Skeleton, cx } from "@/components/ui";
import { api } from "@/lib/api";
import { EFFECT } from "@/lib/format";
import type { Library, LibraryLine } from "@/lib/types";
import { usePoll } from "@/lib/use-poll";

function when(line: LibraryLine): string {
  const parts = Object.entries(line.useWhen).map(([k, v]) => `${k} is ${v.join(" or ")}`);
  return parts.length ? parts.join("; ") : "any market";
}

function LineCard({ line, lib }: { line: LibraryLine; lib: Library }) {
  const [open, setOpen] = useState(false);
  const moves = new Map(lib.moves.map((m) => [m.id, m]));
  return (
    <motion.div layout className="rounded-xl border border-slate-200 bg-white">
      <button onClick={() => setOpen(!open)} className="flex w-full items-start gap-3 p-3.5 text-left">
        <span className="brand-gradient mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-lg text-white"><Route size={15} /></span>
        <div className="min-w-0 flex-1">
          <div className="text-[14px] font-semibold text-slate-900"><span className="font-mono text-[12px] text-slate-500">{line.id}</span> {line.name}</div>
          <div className="text-[12.5px] text-slate-500">{line.purpose}</div>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            <Chip tone="sky">use when {when(line)}</Chip>
            {line.endsProgram && <Chip tone="rose">ends the program</Chip>}
          </div>
        </div>
        <motion.span animate={{ rotate: open ? 180 : 0 }} className="text-slate-400"><ChevronDown size={18} /></motion.span>
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
            <div className="border-t border-slate-100 px-4 py-3">
              <ol className="space-y-2">
                {line.stages.map((stage, i) => (
                  <li key={i} className="flex gap-3">
                    <span className="mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full bg-slate-100 text-[11px] font-semibold text-slate-500">{i + 1}</span>
                    <div className="flex flex-1 flex-wrap gap-2">
                      {stage.map((id) => {
                        const m = moves.get(id);
                        if (!m) return null;
                        return (
                          <div key={id} className="min-w-[220px] flex-1 rounded-lg bg-slate-50 px-3 py-2">
                            <div className="flex flex-wrap items-center gap-1.5 text-[13px] font-medium text-slate-800">
                              <span className="font-mono text-[11.5px] text-slate-500">{m.id}</span> {m.name}
                              <Chip tone={EFFECT[m.effect].tone}>{m.effect}</Chip>
                              {m.effect === "E3" && <Lock size={12} className="text-amber-600" />}
                            </div>
                            <div className="mt-0.5 text-[12px] text-slate-500">{m.tests.join(", ") || "judges or reviews the evidence"}</div>
                          </div>
                        );
                      })}
                    </div>
                  </li>
                ))}
              </ol>
              <p className="mt-3 text-[12px] text-slate-500"><span className="font-semibold text-slate-700">Done when:</span> {line.exit}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

export default function LibraryPage() {
  const { data } = usePoll(api.library, 60000);
  if (!data) return <div className="grid gap-4 md:grid-cols-2"><Skeleton className="h-64" /><Skeleton className="h-64" /></div>;
  const lines = new Map(data.lines.map((l) => [l.id, l]));
  return (
    <div>
      <div className="mb-6">
        <h1 className="text-[26px] font-bold tracking-tight text-slate-900">Line library</h1>
        <p className="mt-1 max-w-3xl text-[14px] text-slate-500">
          The predefined playbook: each task can take the Lines below. A Line is eligible when its conditions hold; the eligible
          Lines are ranked in playbook order and the first is picked. {data.repertoireVersion} · {data.rubricVersion}
        </p>
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        {data.tasks.map((t, i) => (
          <motion.div key={t.id} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.06 * i }}>
            <Card className="h-full p-5">
              <div className="mb-3 flex items-start justify-between gap-3">
                <div>
                  <div className="text-[11px] font-semibold uppercase tracking-wider text-indigo-600">Task {t.id}</div>
                  <div className="text-[17px] font-semibold text-slate-900">{t.name}</div>
                  <div className="text-[13px] text-slate-500">{t.question}</div>
                </div>
                <Chip tone="brand">{t.lines.length} Line{t.lines.length === 1 ? "" : "s"}</Chip>
              </div>
              <div className="space-y-2.5">{t.lines.map((id) => lines.get(id) && <LineCard key={id} line={lines.get(id)!} lib={data} />)}</div>
            </Card>
          </motion.div>
        ))}
      </div>
      <h2 className="mb-3 mt-8 text-[17px] font-semibold text-slate-900">Moves</h2>
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {data.moves.map((m, i) => (
          <motion.div key={m.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.02 * i }}>
            <Card className={cx("h-full p-4")}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[12px] text-slate-500">{m.id}</span>
                <span className="text-[14px] font-semibold text-slate-900">{m.name}</span>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <Chip tone={EFFECT[m.effect].tone}>{m.effect} · {EFFECT[m.effect].label}</Chip>
                {m.tests.map((d) => <Chip key={d} tone="slate">{d}</Chip>)}
              </div>
              <p className="mt-2 text-[12.5px] text-slate-600">{m.does}</p>
              <p className="mt-1.5 text-[12px] text-amber-700">Watch out: {m.watchOut}</p>
            </Card>
          </motion.div>
        ))}
      </div>
    </div>
  );
}
