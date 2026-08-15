import React from 'react';
import { motion } from 'framer-motion';
import { MessagesSquare, FileText, StickyNote, Image, Settings2, FolderGit2, Brain, ArrowRight } from 'lucide-react';

const INPUTS = [
  { icon: MessagesSquare, label: 'Chats' },
  { icon: FileText, label: 'Files' },
  { icon: FolderGit2, label: 'Projects' },
  { icon: StickyNote, label: 'Notes' },
  { icon: Image, label: 'Images' },
  { icon: Settings2, label: 'Instructions' },
];

/**
 * Simple, non-technical explanation of the product:
 * Everything you give your AI -> Our memory layer -> Only the useful information -> Your AI
 */
export default function MemoryLayerVisual({ testId }) {
  return (
    <div data-testid={testId} className="relative w-full rounded-[20px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)]/70 backdrop-blur p-5 sm:p-6 overflow-hidden">
      <div className="absolute inset-0 -z-10">
        <div className="absolute inset-0 bg-[radial-gradient(600px_circle_at_20%_0%,rgba(32,178,170,0.14),transparent_60%)]" />
        <div className="absolute inset-0 bg-grid bg-grid-fade opacity-30" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_auto_1.1fr] gap-5 items-center">
        {/* Inputs */}
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)] mb-3">Everything you give your AI</div>
          <div className="grid grid-cols-2 gap-2">
            {INPUTS.map((it, i) => (
              <motion.div
                key={it.label}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: i * 0.05 }}
                className="flex items-center gap-2 rounded-[10px] border border-[color:var(--border-700)] bg-[color:var(--bg-900)]/60 px-2.5 py-2"
              >
                <it.icon className="w-3.5 h-3.5 text-[color:var(--ink-400)]" />
                <span className="text-xs text-[color:var(--ink-200)]">{it.label}</span>
              </motion.div>
            ))}
          </div>
        </div>

        {/* Arrow / layer */}
        <div className="flex lg:flex-col items-center justify-center gap-3">
          <ArrowRight className="w-5 h-5 text-[color:var(--ink-600)] lg:rotate-0 rotate-90 hidden sm:block" />
          <motion.div
            initial={{ opacity: 0, scale: 0.96 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.3, delay: 0.15 }}
            className="rounded-[14px] border border-[rgba(53,199,191,0.35)] bg-[rgba(32,178,170,0.10)] px-4 py-3 text-center glow-teal"
          >
            <Brain className="w-5 h-5 text-[color:var(--teal-300)] mx-auto" />
            <div className="mt-1 text-xs font-semibold text-[color:var(--teal-300)] whitespace-nowrap">OverHaust</div>
            <div className="text-[10px] text-[color:var(--ink-400)]">memory layer</div>
          </motion.div>
          <ArrowRight className="w-5 h-5 text-[color:var(--ink-600)] lg:rotate-0 rotate-90 hidden sm:block" />
        </div>

        {/* Output */}
        <div>
          <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)] mb-3">Only the useful information → your AI</div>
          <div className="space-y-2">
            {['Keeps what matters', 'Removes unnecessary repetition', 'Remembers important information'].map((t, i) => (
              <motion.div
                key={t}
                initial={{ opacity: 0, x: 8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.25, delay: 0.25 + i * 0.08 }}
                className="flex items-center gap-2 rounded-[10px] border border-[rgba(93,226,180,0.28)] bg-[rgba(93,226,180,0.06)] px-3 py-2"
              >
                <span className="w-1.5 h-1.5 rounded-full bg-[color:var(--mint-400)]" />
                <span className="text-xs text-[color:var(--ink-100)] text-[color:var(--ink-200)]">{t}</span>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
