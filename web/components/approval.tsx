"use client";

import { AnimatePresence, motion } from "motion/react";
import { BadgeCheck, Fingerprint, Lock, Undo2 } from "lucide-react";
import { useState } from "react";
import { ApiError, api } from "@/lib/api";
import { clock, plural, short } from "@/lib/format";
import type { CaseDetail } from "@/lib/types";
import { Button, Card, cx } from "./ui";

/** The human step: approve the agent's plan, bound to its payload hash, or return it with a note. */
export function ApprovalPanel({ detail, onDone }: { detail: CaseDetail; onDone: (d: CaseDetail) => void }) {
  const [returning, setReturning] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const rec = detail.recommendation;
  const state = detail.case.state;

  if (detail.approval) {
    const ok = detail.approval.action === "approve";
    return (
      <motion.div initial={{ opacity: 0, scale: 0.97 }} animate={{ opacity: 1, scale: 1 }}>
        <Card className={cx("p-5", ok ? "bg-emerald-50/60" : "bg-rose-50/60")}>
          <div className="flex items-start gap-3">
            <motion.div initial={{ scale: 0, rotate: -30 }} animate={{ scale: 1, rotate: 0 }} transition={{ type: "spring", stiffness: 260, damping: 14 }}
              className={cx("grid h-10 w-10 place-items-center rounded-full text-white", ok ? "bg-emerald-500" : "bg-rose-500")}>
              {ok ? <BadgeCheck size={20} /> : <Undo2 size={20} />}
            </motion.div>
            <div className="min-w-0">
              <div className="text-[15px] font-semibold text-slate-900">{ok ? "Plan approved" : "Plan returned"}</div>
              <div className="text-[12.5px] text-slate-600">
                by {detail.approval.actor} ({detail.approval.role}) at {clock(detail.approval.at)}
              </div>
              {detail.approval.note && <p className="mt-2 rounded-lg bg-white/70 px-3 py-2 text-[13px] text-slate-700">“{detail.approval.note}”</p>}
              <div className="mt-2 flex items-center gap-1.5 font-mono text-[11px] text-slate-500"><Fingerprint size={12} /> bound to plan {short(detail.approval.payloadHash, 16)}</div>
              {ok && <p className="mt-2 text-[12.5px] text-emerald-800">The Moves may run now. People carry out the Moves that contact people, publish or spend.</p>}
            </div>
          </div>
        </Card>
      </motion.div>
    );
  }

  if (state !== "waiting_review" || !rec || !detail.payloadHash) {
    return (
      <Card className="p-5">
        <div className="flex items-center gap-2 text-[13px] text-slate-500"><Lock size={15} /> The decision opens when the agent has laid out the plan.</div>
      </Card>
    );
  }

  const lines = rec.hypotheses.reduce((n, h) => n + h.tasks.filter((t) => t.lineId).length, 0);
  const gated = rec.hypotheses.reduce((n, h) => n + h.tasks.reduce((k, t) => k + t.moves.filter((m) => m.needsCharter).length, 0), 0);

  async function decide(action: "approve" | "return") {
    setBusy(true);
    setError(null);
    try {
      onDone(await api.decide(detail.case.id, { action, payloadHash: detail.payloadHash ?? "", note }));
    } catch (e) {
      setError(e instanceof ApiError && e.status === 409 ? "The plan changed since it was shown. Reload the case." : String((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
      <Card className="ring-gradient p-5">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-amber-600">Waiting on you</div>
        <div className="mt-1 text-[16px] font-semibold text-slate-900">Approve the agent&apos;s plan?</div>
        <p className="mt-1 text-[13px] text-slate-600">
          {plural(lines, "Line")} across {plural(rec.hypotheses.length, "hypothesis", "hypotheses")}, picked by the playbook. {plural(gated, "Move")} contact people,
          publish or spend; they run only after approval.
        </p>
        <div className="mt-3 flex items-center gap-1.5 rounded-lg bg-slate-50 px-2.5 py-1.5 font-mono text-[11px] text-slate-500">
          <Fingerprint size={12} /> plan {short(detail.payloadHash, 24)}…
        </div>
        <AnimatePresence>
          {returning && (
            <motion.textarea initial={{ height: 0, opacity: 0 }} animate={{ height: 84, opacity: 1 }} exit={{ height: 0, opacity: 0 }}
              value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why it goes back to the customer…"
              className="mt-3 w-full resize-none rounded-xl border border-slate-200 p-3 text-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100" />
          )}
        </AnimatePresence>
        {error && <p className="mt-2 text-[12.5px] text-rose-600">{error}</p>}
        <div className="mt-4 flex gap-2">
          {!returning ? (
            <>
              <Button onClick={() => decide("approve")} disabled={busy} className="flex-1"><BadgeCheck size={16} /> Approve plan</Button>
              <Button variant="outline" onClick={() => setReturning(true)} disabled={busy}><Undo2 size={15} /> Return</Button>
            </>
          ) : (
            <>
              <Button variant="danger" onClick={() => decide("return")} disabled={busy || !note.trim()} className="flex-1">Return with note</Button>
              <Button variant="ghost" onClick={() => setReturning(false)} disabled={busy}>Cancel</Button>
            </>
          )}
        </div>
      </Card>
    </motion.div>
  );
}
