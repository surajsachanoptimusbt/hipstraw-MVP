"use client";

import { motion } from "motion/react";
import { Eye, Mail, MousePointerClick, Search, Users } from "lucide-react";
import { Card, Chip } from "@/components/ui";

// A sample view that shows the offering. Not live data: campaign reviews run today in the CLI (`hipstraw-mm campaign`).
const CHANNELS = [
  { name: "LinkedIn outreach", icon: Users, strategy: "met", readiness: "partly", note: "Audience fits the segment; two assets still in draft" },
  { name: "Email sequence", icon: Mail, strategy: "partly", readiness: "met", note: "Offer is clear; the subject lines promise more than the page" },
  { name: "Search ads", icon: Search, strategy: "unknown", readiness: "not_met", note: "No tracking on the landing page yet: blocker before Day Zero" },
  { name: "Landing page", icon: MousePointerClick, strategy: "met", readiness: "partly", note: "Seller named and claims sourced; consent text missing" },
];
const TONE = { met: "emerald", partly: "sky", not_met: "rose", unknown: "slate" } as const;

export default function Campaigns() {
  return (
    <div>
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="text-[13px] font-semibold text-indigo-600">Campaign management</div>
          <h1 className="mt-1 text-[28px] font-bold tracking-tight text-slate-900">Each channel, tested before and during launch</h1>
          <p className="mt-1 max-w-2xl text-[14px] text-slate-600">Is the message right for the audience each channel reaches, and is the channel ready? Findings and blockers, never a forecast.</p>
        </div>
        <Chip tone="amber"><Eye size={12} /> Preview: sample findings, not live data</Chip>
      </motion.div>
      <div className="grid gap-4 md:grid-cols-2">
        {CHANNELS.map((c, i) => (
          <motion.div key={c.name} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.08 * i }} whileHover={{ y: -3 }}>
            <Card className="h-full p-5">
              <div className="flex items-center gap-3">
                <span className="brand-gradient grid h-10 w-10 place-items-center rounded-xl text-white"><c.icon size={18} /></span>
                <div className="text-[16px] font-semibold text-slate-900">{c.name}</div>
              </div>
              <div className="mt-4 grid grid-cols-2 gap-3">
                <div className="rounded-xl bg-slate-50 p-3"><div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Strategy</div>
                  <div className="mt-1"><Chip tone={TONE[c.strategy as keyof typeof TONE]}>{c.strategy.replace("_", " ")}</Chip></div></div>
                <div className="rounded-xl bg-slate-50 p-3"><div className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Readiness</div>
                  <div className="mt-1"><Chip tone={TONE[c.readiness as keyof typeof TONE]}>{c.readiness.replace("_", " ")}</Chip></div></div>
              </div>
              <p className="mt-3 text-[13px] text-slate-600">{c.note}</p>
            </Card>
          </motion.div>
        ))}
      </div>
      <p className="mt-6 text-[13px] text-slate-500">Campaign reviews run today from the command line (<code className="font-mono text-[12px]">hipstraw-mm campaign</code>) and its own page; they join this workspace next.</p>
    </div>
  );
}
