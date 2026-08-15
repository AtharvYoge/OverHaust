import React, { useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, Loader2 } from 'lucide-react';

const STEPS = [
  { id: 'read', label: 'Reading project context' },
  { id: 'tech', label: 'Detecting technologies' },
  { id: 'arch', label: 'Extracting architecture' },
  { id: 'components', label: 'Finding important components' },
  { id: 'dedupe', label: 'Detecting repeated information' },
  { id: 'stale', label: 'Identifying stale conversation' },
  { id: 'memory', label: 'Building project memory' },
  { id: 'cache', label: 'Generating compressed context cache' },
];

const LOG_LINES = [
  'engine: normalizing inputs…',
  'tokenizer: applying char/4 heuristic',
  'dedupe: fingerprinting repeated architecture notes',
  'architecture: inferring frontend / backend / database',
  'components: scoring by mention density',
  'memory: partitioning conversation into 5 buckets',
  'compressor: writing Context Cache v1',
  'ready: awaiting task-specific relevance query',
];

export default function PipelineOverlay({ open, done, onClose }) {
  const [step, setStep] = useState(0);
  const [logs, setLogs] = useState([]);
  const logRef = useRef(null);

  useEffect(() => {
    if (!open) {
      setStep(0);
      setLogs([]);
      return;
    }
    let cancelled = false;
    setStep(0);
    setLogs([]);

    const advance = async () => {
      for (let i = 0; i < STEPS.length; i++) {
        if (cancelled) return;
        setStep(i);
        setLogs((prev) => [...prev, LOG_LINES[i] || `${STEPS[i].label}…`]);
        // Wait until either backend done OR minimum step delay
        // If done: accelerate remaining steps
        const delay = done ? 220 : 900;
        // eslint-disable-next-line no-await-in-loop
        await new Promise((r) => setTimeout(r, delay));
      }
      if (!cancelled) {
        setStep(STEPS.length);
      }
    };
    advance();
    return () => {
      cancelled = true;
    };
  }, [open, done]);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  useEffect(() => {
    if (open && done && step >= STEPS.length) {
      const t = setTimeout(() => onClose?.(), 480);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [open, done, step, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          key="pipeline"
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
        >
          <div className="absolute inset-0 bg-[color:var(--bg-950)]/80 backdrop-blur-sm" />
          <motion.div
            className="relative w-full max-w-4xl rounded-[16px] border border-[color:var(--border-700)] bg-[color:var(--surface-850)] shadow-[var(--shadow-popover)] overflow-hidden"
            initial={{ y: 8, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            exit={{ y: 8, opacity: 0 }}
            transition={{ duration: 0.22 }}
          >
            <div className="px-6 pt-5 pb-4 border-b border-[color:var(--border-700)] flex items-center justify-between">
              <div>
                <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)]">Context Runtime</div>
                <div className="text-lg font-semibold">Building Context Cache</div>
              </div>
              <div className="text-[11px] font-mono text-[color:var(--ink-400)]">
                {done ? 'llm: complete' : 'llm: analyzing…'}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-[minmax(240px,300px)_1fr] gap-0">
              <ol className="p-4 md:p-5 space-y-2 border-b md:border-b-0 md:border-r border-[color:var(--border-700)] bg-[color:var(--bg-900)]/40">
                {STEPS.map((s, i) => (
                  <li key={s.id} className="flex items-center gap-3">
                    <div
                      className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-mono ${
                        i < step
                          ? 'bg-[rgba(93,226,180,0.14)] text-[color:var(--mint-400)] border border-[rgba(93,226,180,0.35)]'
                          : i === step
                          ? 'bg-[rgba(53,199,191,0.14)] text-[color:var(--teal-300)] border border-[rgba(53,199,191,0.35)]'
                          : 'bg-[color:var(--surface-800)] text-[color:var(--ink-600)] border border-[color:var(--border-700)]'
                      }`}
                    >
                      {i < step ? <Check className="w-3 h-3" /> : i === step ? <Loader2 className="w-3 h-3 animate-spin" /> : i + 1}
                    </div>
                    <span className={`text-sm ${i <= step ? 'text-[color:var(--ink-50)]' : 'text-[color:var(--ink-600)]'}`}>
                      {s.label}
                    </span>
                  </li>
                ))}
              </ol>

              <div className="p-4 md:p-5 flex flex-col">
                <div className="text-[10px] uppercase tracking-[0.14em] text-[color:var(--ink-600)] mb-2">Trace</div>
                <div
                  ref={logRef}
                  className="h-56 md:h-72 overflow-y-auto rounded-md bg-black/40 border border-[color:var(--border-700)] p-3 font-mono text-[12px] leading-6 text-[color:var(--ink-200)]"
                >
                  {logs.map((l, i) => (
                    <div key={i}>
                      <span className="text-[color:var(--ink-600)]">$ </span>
                      <span>{l}</span>
                    </div>
                  ))}
                  {done && step >= STEPS.length && (
                    <div className="mt-2 text-[color:var(--mint-400)]">$ done — Context Cache written.</div>
                  )}
                </div>

                <div className="mt-3">
                  <div className="h-1 rounded-full bg-[color:var(--surface-800)] overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-[color:var(--teal-500)] to-[color:var(--mint-500)] transition-[width] duration-300"
                      style={{ width: `${Math.min(100, (step / STEPS.length) * 100)}%` }}
                    />
                  </div>
                  <div className="mt-2 flex items-center justify-between text-[11px] font-mono text-[color:var(--ink-400)]">
                    <span>step {Math.min(step + 1, STEPS.length)} / {STEPS.length}</span>
                    <span>{done ? 'complete' : 'analyzing'}</span>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
