"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { motion } from "motion/react";
import { cx } from "./ui";

export function Logo({ dark }: { dark?: boolean }) {
  return (
    <Link href="/" className="flex items-center gap-2.5">
      <span className="brand-gradient grid h-8 w-8 place-items-center rounded-xl text-[15px] font-black text-white shadow-lg shadow-indigo-500/30">H</span>
      <span className={cx("text-[16px] font-bold tracking-tight", dark ? "text-white" : "text-slate-900")}>hipstraw</span>
    </Link>
  );
}

type NavItem = { href: string; label: string; exact?: boolean };

function Nav({ items, dark }: { items: NavItem[]; dark?: boolean }) {
  const path = usePathname();
  return (
    <nav className="flex items-center gap-1">
      {items.map((i) => {
        const on = i.exact ? path === i.href : path === i.href || path.startsWith(i.href + "/");
        return (
          <Link key={i.href} href={i.href} className={cx("relative rounded-lg px-3 py-1.5 text-[13.5px] font-medium transition",
            dark ? (on ? "text-white" : "text-slate-400 hover:text-white") : (on ? "text-slate-900" : "text-slate-500 hover:text-slate-900"))}>
            {on && <motion.span layoutId={dark ? "nav-dark" : "nav-light"} className={cx("absolute inset-0 rounded-lg", dark ? "bg-white/10" : "bg-slate-100")} transition={{ type: "spring", stiffness: 380, damping: 30 }} />}
            <span className="relative">{i.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}

/** The reviewer desk: Hipstraw's own view of every request and what the agent is doing with it. */
export function DeskBar() {
  return (
    <header className="sticky top-0 z-30 border-b border-white/5 bg-ink/95 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-6 px-5">
        <Logo dark />
        <span className="hidden rounded-full border border-white/10 px-2.5 py-0.5 text-[11.5px] font-medium text-slate-300 sm:inline">Reviewer desk</span>
        <Nav dark items={[{ href: "/desk", label: "Queue", exact: true }, { href: "/desk/library", label: "Line library" }, { href: "/desk/ledger", label: "Ledger" }]} />
        <div className="flex-1" />
        <Link href="/workspace" className="hidden text-[12.5px] text-slate-400 transition hover:text-white md:inline">Customer workspace →</Link>
        <div className="flex items-center gap-2">
          <span className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-amber-300 to-rose-400 text-[12px] font-bold text-slate-900">HR</span>
          <div className="hidden leading-tight lg:block">
            <div className="text-[12.5px] font-medium text-white">Hipstraw reviewer</div>
            <div className="text-[11px] text-slate-400">reviewer · demo, no sign-in</div>
          </div>
        </div>
      </div>
    </header>
  );
}

/** The customer workspace: the customer's requests and Hipstraw's three offerings. */
export function WorkspaceBar() {
  return (
    <header className="sticky top-0 z-30 border-b border-slate-200/80 bg-white/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1200px] items-center gap-6 px-5">
        <Logo />
        <span className="hidden rounded-full bg-slate-100 px-2.5 py-0.5 text-[11.5px] font-medium text-slate-600 sm:inline">Customer workspace</span>
        <Nav items={[{ href: "/workspace", label: "Home", exact: true }, { href: "/workspace/new", label: "New request" },
          { href: "/workspace/day-zero", label: "Day Zero" }, { href: "/workspace/campaigns", label: "Campaigns" }]} />
        <div className="flex-1" />
        <Link href="/desk" className="hidden text-[12.5px] text-slate-500 transition hover:text-slate-900 md:inline">Reviewer desk →</Link>
        <span className="grid h-8 w-8 place-items-center rounded-full bg-gradient-to-br from-sky-300 to-indigo-400 text-[12px] font-bold text-white">CT</span>
      </div>
    </header>
  );
}
