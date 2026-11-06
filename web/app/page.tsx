"use client";

import Link from "next/link";
import { motion } from "motion/react";
import { ArrowRight, BookOpen, Database, Lock, ShieldCheck, UserCheck, Users } from "lucide-react";
import { Logo } from "@/components/shell";
import { STAGE_ICON, STAGE_ORDER } from "@/components/pipeline";

const NAMES: Record<string, [string, string]> = {
  ingest: ["Ingest", "The request: product, market, evidence"],
  review: ["Review", "Evidence judged against the rubric"],
  position: ["Position", "Where each hypothesis stands"],
  recommend: ["Recommend", "The playbook selects and ranks Lines"],
  workflow: ["Workflow", "Gated Moves, in order"],
  approval: ["Human approval", "Bound to the plan's hash"],
};

function Architecture() {
  return (
    <div className="relative rounded-3xl border border-white/10 bg-white/[0.03] p-6 backdrop-blur">
      <div className="mb-4 flex items-center justify-between">
        <div className="text-[12px] font-semibold uppercase tracking-[0.18em] text-indigo-300">The pipeline</div>
        <div className="text-[11.5px] text-slate-400">Every step on the ledger</div>
      </div>
      <div className="relative">
        <div className="absolute left-6 right-6 top-7 hidden h-0.5 bg-white/10 md:block" />
        <motion.div className="absolute top-[22px] hidden h-3 w-3 rounded-full bg-cyan-300 shadow-[0_0_16px_4px_rgba(103,232,249,0.6)] md:block"
          animate={{ left: ["3%", "95%"] }} transition={{ duration: 5.5, repeat: Infinity, ease: "easeInOut" }} />
        <div className="relative grid grid-cols-3 gap-4 md:grid-cols-6">
          {STAGE_ORDER.map((k, i) => {
            const Icon = STAGE_ICON[k];
            const human = k === "approval";
            return (
              <motion.div key={k} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25 + 0.1 * i }} className="flex flex-col items-center text-center">
                <motion.div animate={{ boxShadow: ["0 0 0 0 rgba(129,140,248,0)", "0 0 0 8px rgba(129,140,248,0.18)", "0 0 0 0 rgba(129,140,248,0)"] }}
                  transition={{ duration: 5.5, repeat: Infinity, delay: (5.5 / 6) * i }}
                  className={`grid h-14 w-14 place-items-center rounded-2xl ${human ? "bg-gradient-to-br from-amber-300 to-rose-400 text-slate-900" : "brand-gradient text-white"}`}>
                  <Icon size={22} />
                </motion.div>
                <div className="mt-2 text-[13px] font-semibold text-white">{i + 1}. {NAMES[k][0]}</div>
                <div className="text-[11.5px] leading-tight text-slate-400">{NAMES[k][1]}</div>
              </motion.div>
            );
          })}
        </div>
      </div>
      <div className="mt-6 grid gap-3 md:grid-cols-3">
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3.5">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-white"><BookOpen size={15} className="text-indigo-300" /> Playbook</div>
          <p className="mt-1 text-[12px] text-slate-400">Predefined Lines and Moves, proven for each scenario. Rules pick them; no model decides.</p>
        </div>
        <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3.5">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-white"><Database size={15} className="text-cyan-300" /> State and audit ledger</div>
          <p className="mt-1 text-[12px] text-slate-400">One SQL transaction per change, an append-only hash chain.</p>
        </div>
        <div className="rounded-2xl border border-dashed border-white/15 p-3.5">
          <div className="flex items-center gap-2 text-[13px] font-semibold text-slate-300"><Lock size={15} /> Not live</div>
          <p className="mt-1 text-[12px] text-slate-500">Jev ranking: deferred. Model API: not used to pick Lines. CRM and mail: not connected.</p>
        </div>
      </div>
    </div>
  );
}

export default function Home() {
  return (
    <div className="min-h-screen bg-ink text-white">
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(900px_500px_at_15%_-10%,rgba(99,102,241,0.35),transparent_60%),radial-gradient(800px_500px_at_100%_10%,rgba(168,85,247,0.25),transparent_60%)]" />
      <div className="relative mx-auto max-w-[1200px] px-6">
        <header className="flex h-16 items-center justify-between"><Logo dark />
          <div className="flex gap-2 text-[13px]"><Link href="/workspace" className="rounded-lg px-3 py-1.5 text-slate-300 hover:text-white">Customer workspace</Link>
            <Link href="/desk" className="rounded-lg bg-white/10 px-3 py-1.5 font-medium text-white hover:bg-white/15">Reviewer desk</Link></div>
        </header>
        <section className="pb-10 pt-14">
          <motion.div initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.6 }}>
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-[12px] text-slate-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Shadow launch platform · humans and agents together
            </div>
            <h1 className="mt-5 max-w-3xl text-[44px] font-bold leading-[1.05] tracking-tight md:text-[56px]">
              See exactly what the agent does, <span className="bg-gradient-to-r from-indigo-300 via-violet-300 to-cyan-300 bg-clip-text text-transparent">and why.</span>
            </h1>
            <p className="mt-5 max-w-2xl text-[16px] leading-relaxed text-slate-300">
              Requests come in. The agent works each one through a fixed pipeline, the playbook picks proven Lines and Moves,
              and a reviewer approves before anything contacts people or spends.
            </p>
          </motion.div>
          <div className="mt-8 grid gap-4 md:grid-cols-2">
            {[
              { href: "/desk", icon: UserCheck, title: "Reviewer desk", text: "The queue of requests, the agent at work, the Lines it picked, and your approvals.", tone: "from-amber-300 to-rose-400 text-slate-900" },
              { href: "/workspace", icon: Users, title: "Customer workspace", text: "Send a request, follow it live, and see the plan for shadow launch, Day Zero and campaigns.", tone: "brand-gradient text-white" },
            ].map((c, i) => (
              <motion.div key={c.href} initial={{ opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.15 + 0.1 * i }} whileHover={{ y: -4 }}>
                <Link href={c.href} className="group flex items-center gap-4 rounded-3xl border border-white/10 bg-white/[0.05] p-5 transition hover:border-white/25 hover:bg-white/[0.08]">
                  <span className={`grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br ${c.tone}`}><c.icon size={22} /></span>
                  <div className="flex-1"><div className="text-[17px] font-semibold">{c.title}</div><div className="text-[13px] text-slate-400">{c.text}</div></div>
                  <ArrowRight className="text-slate-500 transition group-hover:translate-x-1 group-hover:text-white" />
                </Link>
              </motion.div>
            ))}
          </div>
        </section>
        <section className="pb-16"><Architecture /></section>
        <footer className="flex items-center gap-2 border-t border-white/10 py-6 text-[12px] text-slate-500"><ShieldCheck size={14} /> Findings and plans, never a sales forecast. Demo: no sign-in.</footer>
      </div>
    </div>
  );
}
