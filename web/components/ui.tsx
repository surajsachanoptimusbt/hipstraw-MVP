"use client";

import { animate, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { STATE, TONE, WAITING, type Tone } from "@/lib/format";
import type { CaseState, WaitingOn } from "@/lib/types";

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

export function Chip({ tone = "slate", children, className, pulse }: {
  tone?: Tone; children: React.ReactNode; className?: string; pulse?: boolean;
}) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset", TONE[tone].chip, className)}>
      {pulse !== undefined && <Dot tone={tone} pulse={pulse} />}
      {children}
    </span>
  );
}

export function Dot({ tone, pulse }: { tone: Tone; pulse?: boolean }) {
  return (
    <span className="relative inline-flex h-2 w-2">
      {pulse && <span className={cx("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", TONE[tone].dot)} />}
      <span className={cx("relative inline-flex h-2 w-2 rounded-full", TONE[tone].dot)} />
    </span>
  );
}

export function StatePill({ state, customer }: { state: CaseState; customer?: boolean }) {
  const s = STATE[state];
  return <Chip tone={s.tone} pulse={state === "agent_working"}>{customer ? s.customer : s.label}</Chip>;
}

export function WaitingLabel({ waiting }: { waiting: WaitingOn }) {
  const w = WAITING[waiting];
  return <span className={cx("text-sm font-medium", TONE[w.tone].text)}>{w.label}</span>;
}

export function Card({ children, className }: { children: React.ReactNode; className?: string }) {
  return <div className={cx("rounded-2xl border border-slate-200/80 bg-white shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.08)]", className)}>{children}</div>;
}

export function SectionTitle({ title, hint, right }: { title: string; hint?: string; right?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-end justify-between gap-4">
      <div>
        <h2 className="text-[15px] font-semibold tracking-tight text-slate-900">{title}</h2>
        {hint && <p className="mt-0.5 text-sm text-slate-500">{hint}</p>}
      </div>
      {right}
    </div>
  );
}

export function Button({ children, onClick, variant = "primary", disabled, type = "button", className }: {
  children: React.ReactNode; onClick?: () => void; variant?: "primary" | "ghost" | "outline" | "danger";
  disabled?: boolean; type?: "button" | "submit"; className?: string;
}) {
  const styles = {
    primary: "brand-gradient text-white shadow-lg shadow-indigo-500/25 hover:brightness-110",
    outline: "border border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
    ghost: "text-slate-600 hover:bg-slate-100",
    danger: "border border-rose-200 bg-rose-50 text-rose-700 hover:bg-rose-100",
  }[variant];
  return (
    <motion.button type={type} whileTap={{ scale: 0.97 }} onClick={onClick} disabled={disabled}
      className={cx("inline-flex items-center justify-center gap-2 rounded-xl px-4 py-2 text-sm font-semibold transition disabled:cursor-not-allowed disabled:opacity-50", styles, className)}>
      {children}
    </motion.button>
  );
}

/** A number that counts up to its value when it appears or changes. */
export function CountUp({ value, className }: { value: number; className?: string }) {
  const [shown, setShown] = useState(0);
  const from = useRef(0);
  useEffect(() => {
    const controls = animate(from.current, value, {
      duration: 0.9, ease: "easeOut", onUpdate: (v) => setShown(Math.round(v)),
    });
    from.current = value;
    return () => controls.stop();
  }, [value]);
  return <span className={className}>{shown}</span>;
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("shimmer rounded-xl", className)} />;
}

export function Mono({ children, className }: { children: React.ReactNode; className?: string }) {
  return <span className={cx("font-mono text-[12px]", className)}>{children}</span>;
}
