"use client";

import { AnimatePresence, motion } from "motion/react";
import { BadgeCheck, Cpu, Inbox, Route, ScanSearch, ShieldCheck, RotateCcw } from "lucide-react";
import { useEffect, useRef } from "react";
import { clock, words } from "@/lib/format";
import type { EventKind, LedgerEvent } from "@/lib/types";
import { cx } from "./ui";

const KIND: Record<EventKind, { icon: typeof Cpu; bubble: string; label: string }> = {
  request: { icon: Inbox, bubble: "bg-sky-100 text-sky-700", label: "Request" },
  step: { icon: Cpu, bubble: "bg-indigo-100 text-indigo-700", label: "Step" },
  finding: { icon: ScanSearch, bubble: "bg-violet-100 text-violet-700", label: "Finding" },
  pick: { icon: Route, bubble: "brand-gradient text-white", label: "Line picked" },
  gate: { icon: ShieldCheck, bubble: "bg-amber-100 text-amber-700", label: "Gate" },
  decision: { icon: BadgeCheck, bubble: "bg-emerald-100 text-emerald-700", label: "Decision" },
};

/** What the agent is doing: each ledger event as it happens, newest at the bottom. */
export function ActivityFeed({ events, working, replaying, onReplay, compact }: {
  events: LedgerEvent[]; working: boolean; replaying?: boolean; onReplay?: () => void; compact?: boolean;
}) {
  const end = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = box.current;
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [events.length]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-slate-100 px-5 py-3.5">
        <div>
          <div className="text-[15px] font-semibold text-slate-900">What the agent is doing</div>
          <div className="text-xs text-slate-500">Every step is written to the ledger as it happens</div>
        </div>
        {onReplay && (
          <button onClick={onReplay} disabled={replaying || working}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-200 px-2.5 py-1.5 text-xs font-medium text-slate-600 transition hover:border-indigo-300 hover:text-indigo-700 disabled:opacity-40">
            <RotateCcw size={13} /> {replaying ? "Replaying…" : "Replay run"}
          </button>
        )}
      </div>
      <div ref={box} className={cx("scroll-thin flex-1 overflow-y-auto px-5 py-4", compact ? "max-h-[420px]" : "max-h-[640px]")}>
        <ol className="relative space-y-3.5">
          <span className="absolute bottom-2 left-[15px] top-2 w-px bg-slate-200" />
          <AnimatePresence initial={false}>
            {events.map((e) => {
              const k = KIND[e.kind];
              const Icon = k.icon;
              return (
                <motion.li key={e.seq} layout initial={{ opacity: 0, x: -14, scale: 0.98 }} animate={{ opacity: 1, x: 0, scale: 1 }}
                  transition={{ type: "spring", stiffness: 380, damping: 30 }} className="relative flex gap-3">
                  <div className={cx("relative z-10 mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-full ring-4 ring-white", k.bubble)}>
                    <Icon size={15} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline gap-x-2">
                      <span className={cx("text-[13.5px] font-semibold", e.kind === "pick" ? "text-indigo-800" : "text-slate-800")}>{e.title}</span>
                    </div>
                    {e.detail && <p className="mt-0.5 text-[12.5px] leading-relaxed text-slate-600">{e.detail}</p>}
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-400">
                      <span>{clock(e.at)}</span><span>·</span><span>{words(e.stage)}</span><span>·</span>
                      <span>{e.who}</span><span>·</span><span className="font-mono">#{e.seq} {e.hash.slice(0, 8)}</span>
                    </div>
                  </div>
                </motion.li>
              );
            })}
          </AnimatePresence>
          {(working || replaying) && (
            <motion.li initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="relative flex items-center gap-3">
              <div className="relative z-10 grid h-8 w-8 place-items-center rounded-full bg-white ring-4 ring-white">
                <span className="flex gap-0.5">
                  {[0, 1, 2].map((i) => (
                    <motion.span key={i} className="h-1.5 w-1.5 rounded-full bg-indigo-500"
                      animate={{ y: [0, -4, 0] }} transition={{ duration: 0.8, repeat: Infinity, delay: i * 0.15 }} />
                  ))}
                </span>
              </div>
              <div className="shimmer h-4 w-48 rounded-md" />
            </motion.li>
          )}
          <div ref={end} />
        </ol>
      </div>
    </div>
  );
}
