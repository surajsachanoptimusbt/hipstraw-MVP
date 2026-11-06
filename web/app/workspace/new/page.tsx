"use client";

import { useRouter } from "next/navigation";
import { AnimatePresence, motion } from "motion/react";
import { Plus, Send, Sparkles, Trash2 } from "lucide-react";
import { useState } from "react";
import { Button, Card, cx } from "@/components/ui";
import { api } from "@/lib/api";

type Hyp = {
  name: string; demand: string; segment: string; profile: string; offering: string; description: string;
  recurring: boolean; price: string; per: string; triggers: string; buyerRole: string;
};

const EMPTY: Hyp = { name: "", demand: "", segment: "", profile: "small_business", offering: "", description: "", recurring: false, price: "", per: "month", triggers: "", buyerRole: "" };

const EXAMPLE = {
  product: "Zimplii", market: "Independent Technical Service Assurance", geography: "Metro Atlanta first",
  statement: "Businesses that depend on external technology providers lack independent assurance over what they were promised and what was delivered.",
  buyer: "b2b", motion: "self_serve",
  hypotheses: [{
    name: "Pre-engagement verification", demand: "Businesses choosing a software provider will pay to verify it before signing",
    segment: "Metro Atlanta businesses, 5-50 staff, choosing a software development provider", profile: "small_business",
    offering: "Pre-engagement provider verification", description: "A fixed-price check of a provider's identity, competence and claims",
    recurring: false, price: "", per: "month", triggers: "a provider shortlist, a statement of work about to be signed",
    buyerRole: "the owner choosing the provider",
  }],
};

const input = "w-full rounded-xl border border-slate-200 bg-white px-3.5 py-2.5 text-[14px] outline-none transition placeholder:text-slate-400 focus:border-indigo-400 focus:ring-4 focus:ring-indigo-100";

function Field({ label, hint, children, className }: { label: string; hint?: string; children: React.ReactNode; className?: string }) {
  return (
    <label className={cx("block", className)}>
      <span className="text-[13px] font-medium text-slate-700">{label}</span>
      {hint && <span className="ml-1.5 text-[12px] text-slate-400">{hint}</span>}
      <div className="mt-1.5">{children}</div>
    </label>
  );
}

export default function NewRequest() {
  const router = useRouter();
  const [f, setF] = useState({ product: "", market: "", geography: "", statement: "", buyer: "b2b", motion: "sales_led" });
  const [hyps, setHyps] = useState<Hyp[]>([{ ...EMPTY }]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const setH = (i: number, patch: Partial<Hyp>) => setHyps(hyps.map((h, j) => (j === i ? { ...h, ...patch } : h)));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = {
        ...f,
        hypotheses: hyps.map((h) => ({
          name: h.name, demand: h.demand, segment: h.segment, profile: h.profile, offering: h.offering,
          description: h.description, recurring: h.recurring, buyerRole: h.buyerRole,
          triggers: h.triggers.split(",").map((t) => t.trim()).filter(Boolean),
          priceFloor: h.price ? { amount: Number(h.price), currency: "USD", per: h.per } : null,
        })),
      };
      const made = await api.submit(body, { actor: `${f.product || "Customer"} team`, role: "customer" });
      router.push(`/workspace/requests/${made.id}`);
    } catch (err) {
      setError((err as Error).message);
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="mx-auto max-w-3xl">
      <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="text-[13px] font-semibold text-indigo-600">Shadow launch · Market validation</div>
          <h1 className="mt-1 text-[28px] font-bold tracking-tight text-slate-900">Validate demand for your market</h1>
          <p className="mt-1 text-[14px] text-slate-600">Market discovery chose the market. Tell us who you believe will buy what; Hipstraw plans how to prove it.</p>
        </div>
        <Button variant="outline" onClick={() => {
          const { hypotheses, ...thesis } = EXAMPLE;
          setF(thesis);
          setHyps(hypotheses.map((h) => ({ ...h })));
        }}>
          <Sparkles size={15} /> Use the Zimplii example
        </Button>
      </motion.div>

      <Card className="mb-5 p-6">
        <div className="mb-4 text-[15px] font-semibold text-slate-900">Your product and market</div>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Product"><input className={input} value={f.product} onChange={(e) => setF({ ...f, product: e.target.value })} placeholder="Your product" required /></Field>
          <Field label="Market"><input className={input} value={f.market} onChange={(e) => setF({ ...f, market: e.target.value })} placeholder="The market discovery recommended" required /></Field>
          <Field label="Where" hint="optional"><input className={input} value={f.geography} onChange={(e) => setF({ ...f, geography: e.target.value })} placeholder="City, region or country" /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Buyer"><select className={input} value={f.buyer} onChange={(e) => setF({ ...f, buyer: e.target.value })}><option value="b2b">Businesses</option><option value="b2c">Consumers</option></select></Field>
            <Field label="Sold"><select className={input} value={f.motion} onChange={(e) => setF({ ...f, motion: e.target.value })}><option value="sales_led">By a person</option><option value="self_serve">From a page</option></select></Field>
          </div>
          <Field label="Thesis" hint="who you serve, with what" className="md:col-span-2">
            <textarea className={cx(input, "min-h-[84px] resize-y")} value={f.statement} onChange={(e) => setF({ ...f, statement: e.target.value })} required minLength={10} />
          </Field>
        </div>
      </Card>

      <AnimatePresence initial={false}>
        {hyps.map((h, i) => (
          <motion.div key={i} initial={{ opacity: 0, height: 0 }} animate={{ opacity: 1, height: "auto" }} exit={{ opacity: 0, height: 0 }} className="overflow-hidden">
            <Card className="mb-5 p-6">
              <div className="mb-4 flex items-center justify-between">
                <div className="text-[15px] font-semibold text-slate-900">Demand hypothesis H{i + 1}</div>
                {hyps.length > 1 && <button type="button" onClick={() => setHyps(hyps.filter((_, j) => j !== i))} className="text-slate-400 hover:text-rose-600"><Trash2 size={16} /></button>}
              </div>
              <div className="grid gap-4 md:grid-cols-2">
                <Field label="Name"><input className={input} value={h.name} onChange={(e) => setH(i, { name: e.target.value })} placeholder="Short name" required /></Field>
                <Field label="Kind of buyer"><select className={input} value={h.profile} onChange={(e) => setH(i, { profile: e.target.value })}>
                  <option value="small_business">Small business</option><option value="mid_market">Mid-market</option><option value="enterprise">Enterprise</option></select></Field>
                <Field label="The demand" hint="who will do what" className="md:col-span-2"><input className={input} value={h.demand} onChange={(e) => setH(i, { demand: e.target.value })} required /></Field>
                <Field label="Segment"><input className={input} value={h.segment} onChange={(e) => setH(i, { segment: e.target.value })} required /></Field>
                <Field label="Offering"><input className={input} value={h.offering} onChange={(e) => setH(i, { offering: e.target.value })} required /></Field>
                <Field label="Who decides and pays"><input className={input} value={h.buyerRole} onChange={(e) => setH(i, { buyerRole: e.target.value })} placeholder="e.g. the owner" /></Field>
                <Field label="Buying triggers" hint="comma separated"><input className={input} value={h.triggers} onChange={(e) => setH(i, { triggers: e.target.value })} /></Field>
                <Field label="Price floor (USD)" hint="optional">
                  <div className="flex gap-2"><input className={input} type="number" min={1} value={h.price} onChange={(e) => setH(i, { price: e.target.value })} />
                    <select className={cx(input, "w-36")} value={h.per} onChange={(e) => setH(i, { per: e.target.value })}><option value="month">per month</option><option value="year">per year</option><option value="engagement">per engagement</option></select></div>
                </Field>
                <label className="flex cursor-pointer items-center gap-3 self-end rounded-xl border border-slate-200 px-3.5 py-2.5">
                  <input type="checkbox" checked={h.recurring} onChange={(e) => setH(i, { recurring: e.target.checked })} className="h-4 w-4 accent-indigo-600" />
                  <span className="text-[14px] text-slate-700">Bought again and again</span>
                </label>
              </div>
            </Card>
          </motion.div>
        ))}
      </AnimatePresence>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="outline" onClick={() => setHyps([...hyps, { ...EMPTY }])} disabled={hyps.length >= 5}><Plus size={15} /> Add a hypothesis</Button>
        <Button type="submit" disabled={busy}><Send size={15} /> {busy ? "Sending…" : "Send to Hipstraw"}</Button>
      </div>
      {error && <p className="mt-3 rounded-xl bg-rose-50 px-4 py-3 text-[13px] text-rose-700">{error}</p>}
    </form>
  );
}
