"use client";

import { motion } from "motion/react";
import { Bot } from "lucide-react";

/** The agent: it breathes and orbits while it works, and rests when it is waiting on a person. */
export function AgentOrb({ working, size = 52 }: { working: boolean; size?: number }) {
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }}>
      {working && (
        <>
          <motion.span className="absolute inset-0 rounded-full bg-indigo-500/30"
            animate={{ scale: [1, 1.7], opacity: [0.5, 0] }} transition={{ duration: 1.6, repeat: Infinity, ease: "easeOut" }} />
          <motion.span className="absolute inset-0" animate={{ rotate: 360 }} transition={{ duration: 3, repeat: Infinity, ease: "linear" }}>
            <span className="absolute -top-0.5 left-1/2 h-2 w-2 -translate-x-1/2 rounded-full bg-violet-400 shadow-[0_0_10px_#a78bfa]" />
          </motion.span>
          <motion.span className="absolute inset-1" animate={{ rotate: -360 }} transition={{ duration: 4.5, repeat: Infinity, ease: "linear" }}>
            <span className="absolute bottom-0 left-1/2 h-1.5 w-1.5 -translate-x-1/2 rounded-full bg-cyan-300 shadow-[0_0_8px_#67e8f9]" />
          </motion.span>
        </>
      )}
      <motion.div className="brand-gradient relative grid place-items-center rounded-full text-white shadow-lg shadow-indigo-500/30"
        style={{ width: size * 0.78, height: size * 0.78 }}
        animate={working ? { scale: [1, 1.06, 1] } : { scale: 1 }}
        transition={working ? { duration: 1.4, repeat: Infinity, ease: "easeInOut" } : undefined}>
        <Bot size={size * 0.38} strokeWidth={2} />
      </motion.div>
    </div>
  );
}
