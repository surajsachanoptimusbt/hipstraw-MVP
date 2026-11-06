"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { Link2, ShieldAlert, ShieldCheck } from "lucide-react";
import { Card, Chip, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { clock, short, words } from "@/lib/format";
import { usePoll } from "@/lib/use-poll";

export default function LedgerPage() {
  const { data } = usePoll(api.ledger, 3000);
  if (!data) return <Skeleton className="h-96" />;
  const v = data.verify;
  return (
    <div>
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-[26px] font-bold tracking-tight text-slate-900">Ledger</h1>
          <p className="mt-1 max-w-2xl text-[14px] text-slate-500">Every step of every case, appended in one SQL transaction with the change it records.
            Each entry carries the hash of the one before it, so an edited or removed entry breaks the chain.</p>
        </div>
        <motion.div initial={{ scale: 0.9, opacity: 0 }} animate={{ scale: 1, opacity: 1 }}>
          <Card className={v.ok ? "flex items-center gap-3 bg-emerald-50 px-4 py-3" : "flex items-center gap-3 bg-rose-50 px-4 py-3"}>
            {v.ok ? <ShieldCheck className="text-emerald-600" /> : <ShieldAlert className="text-rose-600" />}
            <div>
              <div className="text-[14px] font-semibold text-slate-900">{v.ok ? "Chain intact" : `Chain broken at #${v.brokenAt}`}</div>
              <div className="text-[12px] text-slate-500">{v.checked} of {data.total} entries checked · head {short(v.head, 12)}</div>
            </div>
          </Card>
        </motion.div>
      </div>
      <ol className="relative space-y-0">
        {data.events.map((e, i) => (
          <motion.li key={e.seq} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i, 30) * 0.02 }} className="relative pb-3 pl-10">
            {i < data.events.length - 1 && <span className="absolute bottom-0 left-[15px] top-8 w-px bg-gradient-to-b from-indigo-300 to-slate-200" />}
            <span className="absolute left-0 top-2 grid h-8 w-8 place-items-center rounded-lg bg-white text-indigo-600 shadow ring-1 ring-slate-200"><Link2 size={14} /></span>
            <Card className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3">
              <span className="font-mono text-[12px] font-semibold text-slate-500">#{e.seq}</span>
              <Link href={`/desk/cases/${e.caseId}`} className="font-mono text-[12px] text-indigo-700 hover:underline">{e.caseId}</Link>
              <Chip tone={e.actor === "reviewer" ? "amber" : e.actor === "customer" ? "sky" : "brand"}>{e.actor}</Chip>
              <span className="min-w-0 flex-1 truncate text-[13.5px] font-medium text-slate-800">{e.title}</span>
              <span className="text-[11.5px] text-slate-400">{words(e.stage)} · {clock(e.at)}</span>
              <span className="w-full font-mono text-[11px] text-slate-400">hash {short(e.hash, 20)} ← prev {short(e.prevHash, 20)}</span>
            </Card>
          </motion.li>
        ))}
      </ol>
    </div>
  );
}
